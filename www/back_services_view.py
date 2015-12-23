# -*- coding: utf8 -*-
import uuid
import hashlib
import json

from django.db import transaction
from django.views.decorators.cache import never_cache
from django.template.response import TemplateResponse
from django.http import JsonResponse
from www.views import AuthedView, LeftSideBarMixin
from www.decorator import perm_required
from www.models import ServiceInfo, TenantRegionInfo, TenantServiceInfo, TenantServiceAuth, TenantServiceRelation, AppServiceInfo
from service_http import RegionServiceApi
from www.tenantservice.baseservice import BaseTenantService, TenantUsedResource
from www.monitorservice.monitorhook import MonitorHook

import logging
logger = logging.getLogger('default')

regionClient = RegionServiceApi()
baseService = BaseTenantService()
tenantUsedResource = TenantUsedResource()
monitorhook = MonitorHook()


class ServiceMarket(LeftSideBarMixin, AuthedView):

    def get_media(self):
        media = super(AuthedView, self).get_media() + self.vendor(
            'www/assets/jquery-easy-pie-chart/jquery.easy-pie-chart.css', 'www/css/owl.carousel.css',
            'www/css/goodrainstyle.css', 'www/js/jquery.cookie.js', 'www/js/common-scripts.js',
            'www/js/jquery.dcjqaccordion.2.7.js', 'www/js/jquery.scrollTo.min.js', 'www/js/back-service-create.js')
        return media

    @never_cache
    @perm_required('tenant_access')
    def get(self, request, *args, **kwargs):
        try:
            context = self.get_context()
            if self.user.is_sys_admin:
                cacheServiceList = ServiceInfo.objects.all()
            else:
                cacheServiceList = ServiceInfo.objects.filter(status="published")
            context["cacheServiceList"] = cacheServiceList
            context["serviceMarketStatus"] = "active"
            context["tenantName"] = self.tenantName
        except Exception as e:
            logger.exception(e)
        return TemplateResponse(self.request, "www/service_market.html", context)


class ServiceMarketDeploy(LeftSideBarMixin, AuthedView):

    def get_media(self):
        media = super(AuthedView, self).get_media() + self.vendor(
            'www/assets/jquery-easy-pie-chart/jquery.easy-pie-chart.css', 'www/css/owl.carousel.css',
            'www/css/goodrainstyle.css', 'www/js/jquery.cookie.js', 'www/js/common-scripts.js',
            'www/js/jquery.dcjqaccordion.2.7.js', 'www/js/jquery.scrollTo.min.js', 'www/js/back-service-create.js')
        return media

    def find_dependecy_services(self, serviceObj):
        if serviceObj.dependecy is None:
            return {}
        else:
            tenant_id = self.tenant.tenant_id
            dependecy_keys = serviceObj.dependecy.split(',')
            dependecy_keys.append('redis')
            deployTenantServices = TenantServiceInfo.objects.filter(tenant_id=tenant_id, service_key__in=dependecy_keys, service_region=self.response_region)
            dependecy_services = dict((el, []) for el in dependecy_keys)
            for s in deployTenantServices:
                dependecy_services[s.service_key].append(s)
            return dependecy_services

    @never_cache
    @perm_required('code_deploy')
    def get(self, request, *args, **kwargs):
        context = self.get_context()
        try:
            service_key = request.GET.get("service_key", "")
            if service_key == "":
                return self.redirect_to('/apps/{0}/service/'.format(self.tenant.tenant_name))

            context["serviceMarketStatus"] = "active"

            serviceObj = ServiceInfo.objects.get(service_key=service_key)
            context["service"] = serviceObj
            context["dependecy_services"] = self.find_dependecy_services(serviceObj)
            context["tenantName"] = self.tenantName
            context["service_key"] = service_key
        except Exception as e:
            logger.exception(e)
        return TemplateResponse(self.request, "www/back_service_create_step_1.html", context)

    @never_cache
    @perm_required('code_deploy')
    def post(self, request, *args, **kwargs):
        logger.debug('debug', request.POST)
        return JsonResponse({"status": "exist"}, status=200)
        service_alias = ""
        uid = str(uuid.uuid4()) + self.tenant.tenant_id
        service_id = hashlib.md5(uid.encode("UTF-8")).hexdigest()
        result = {}
        try:
            self.tenant_region = TenantRegionInfo.objects.get(tenant_id=self.tenant.tenant_id, region_name=self.response_region)
            if self.tenant_region.service_status == 2 and self.tenant.pay_type == "payed":
                result["status"] = "owed"
                return JsonResponse(result, status=200)

            tenant_id = self.tenant.tenant_id

            service_key = request.POST.get("service_key", "")
            if service_key == "":
                result["status"] = "notexist"
                return JsonResponse(result, status=200)

            service_alias = request.POST.get("create_service_name", "")
            if service_alias == "":
                result["status"] = "empty"
                return JsonResponse(result, status=200)

            service_alias = service_alias.lower()
            num = TenantServiceInfo.objects.filter(tenant_id=tenant_id, service_alias=service_alias).count()
            if num > 0:
                result["status"] = "exist"
                return JsonResponse(result, status=200)

            service = ServiceInfo.objects.get(service_key=service_key)
            service_memory = request.POST.get("service_memory", "")
            if service_memory != "":
                cm = int(service_memory)
                if cm >= 128:
                    ccpu = int(cm / 128) * 20
                    service.min_cpu = ccpu
                    service.min_memory = cm
            logger.debug(service.min_memory)
            createService = request.POST.get("createService", "")
            logger.debug(createService)
            dependencyNum = 0
            serviceKeys = createService.split(",")
            if createService != "":
                dependencyNum = len(serviceKeys)
            # calculate resource
            flag = tenantUsedResource.predict_next_memory(self.tenant, dependencyNum * 128 + service.min_memory)
            if not flag:
                if self.tenant.pay_type == "free":
                    result["status"] = "over_memory"
                else:
                    result["status"] = "over_money"
                return JsonResponse(result, status=200)
            # create new service
            if createService != "":
                for skey in serviceKeys:
                    try:
                        dep_service = ServiceInfo.objects.get(service_key=skey)
                        tempUuid = str(uuid.uuid4()) + skey
                        dep_service_id = hashlib.md5(tempUuid.encode("UTF-8")).hexdigest()
                        depTenantService = baseService.create_service(
                            dep_service_id, tenant_id, dep_service.service_key + "_" + service_alias, dep_service, self.user.pk, region=self.response_region)
                        monitorhook.serviceMonitor(self.user.nick_name, depTenantService, 'create_service', True)
                        baseService.create_region_service(depTenantService, self.tenantName, self.response_region, self.user.nick_name)
                        monitorhook.serviceMonitor(self.user.nick_name, depTenantService, 'init_region_service', True)
                        baseService.create_service_env(tenant_id, dep_service_id, self.response_region)
                        baseService.create_service_dependency(tenant_id, service_id, dep_service_id, self.response_region)
                    except Exception as e:
                        logger.exception(e)

            # exist service dependency
            hasService = request.POST.get("hasService", "")
            logger.debug(hasService)
            if hasService != "":
                serviceIds = hasService.split(",")
                for sid in serviceIds:
                    try:
                        baseService.create_service_dependency(tenant_id, service_id, sid, self.response_region)
                    except Exception as e:
                        logger.exception(e)

            # create console service

            newTenantService = baseService.create_service(
                service_id, tenant_id, service_alias, service, self.user.pk, region=self.response_region)

            if service.category == 'app_publish':
                newTenantService = self.update_app_service(service, newTenantService)

            monitorhook.serviceMonitor(self.user.nick_name, newTenantService, 'create_service', True)

            # create region tenantservice
            baseService.create_region_service(newTenantService, self.tenantName, self.response_region, self.user.nick_name)
            monitorhook.serviceMonitor(self.user.nick_name, newTenantService, 'init_region_service', True)

            # create service env
            baseService.create_service_env(tenant_id, service_id, self.response_region)

            result["status"] = "success"
            result["service_id"] = service_id
            result["service_alias"] = service_alias
        except Exception as e:
            logger.exception(e)
            TenantServiceInfo.objects.filter(service_id=service_id).delete()
            TenantServiceAuth.objects.filter(service_id=service_id).delete()
            TenantServiceRelation.objects.get(service_id=service_id).delete()
            result["status"] = "failure"
        return JsonResponse(result, status=200)

    def update_app_service(self, service, newTenantService):
        with transaction.atomic():
            appversion = AppServiceInfo.objects.defer('change_log').get(service_key=service.service_key, app_version=service.version)
            appversion.deploy_num += 1
            appversion.view_num += 1
            appversion.save(update_fields=['deploy_num', 'view_num'])

        newTenantService, update_fields = self.copy_properties(appversion, newTenantService)
        newTenantService.save(update_fields=update_fields)
        return newTenantService

    def copy_properties(self, copy_from, to):
        update_fields = []
        for field in ('deploy_version', 'cmd', 'setting', 'image', 'dependecy', 'env'):
            if hasattr(to, field) and hasattr(copy_from, field):
                to_value = getattr(to, field)
                from_value = getattr(copy_from, field)
                if to_value != from_value:
                    setattr(to, field, from_value)
                    update_fields.append(field)
        return to, update_fields
