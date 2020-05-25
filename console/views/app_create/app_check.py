# -*- coding: utf8 -*-
"""
  Created on 18/2/1.
"""
from re import split as re_spilt
from django.views.decorators.cache import never_cache
from rest_framework.response import Response

from console.views.app_config.base import AppBaseView
from console.utils.oauth.oauth_types import support_oauth_type
from console.services.app_check_service import app_check_service
from console.services.app import app_service
from www.utils.return_message import general_message
import logging
from console.serializer import TenantServiceUpdateSerilizer

logger = logging.getLogger("default")


class AppCheck(AppBaseView):
    @never_cache
    def get(self, request, *args, **kwargs):
        """
        获取组件检测信息
        ---
        parameters:
            - name: tenantName
              description: 租户名
              required: true
              type: string
              paramType: path
            - name: serviceAlias
              description: 组件别名
              required: true
              type: string
              paramType: path
            - name: check_uuid
              description: 检测id
              required: true
              type: string
              paramType: query

        """
        check_uuid = request.GET.get("check_uuid", None)
        if not check_uuid:
            return Response(general_message(400, "params error", "参数错误，请求参数应该包含请求的ID"), status=400)
        code, msg, data = app_check_service.get_service_check_info(self.tenant, self.service.service_region, check_uuid)
        logger.debug("check resp! {0}".format(data))
        # 如果已创建完成
        if self.service.create_status == "complete":
            service_info = data.get("service_info")
            if service_info is not None and len(service_info) > 1 and service_info[0].get("language") == "Java-maven":
                pass
            else:
                app_check_service.update_service_check_info(self.tenant, self.service, data)
            check_brief_info = app_check_service.wrap_service_check_info(self.service, data)
            return Response(general_message(200, "success", "请求成功", bean=check_brief_info))

        if data["service_info"] and len(data["service_info"]) < 2:
            # No need to save env, ports and other information for multiple services here.
            logger.debug("start save check info ! {0}".format(self.service.create_status))
            save_code, save_msg = app_check_service.save_service_check_info(self.tenant, self.service, data)
            if save_code != 200:
                data["check_status"] = "failure"
                save_error = {
                    "error_type": "check info save error",
                    "solve_advice": "修改相关信息后重新尝试",
                    "error_info": "{}".format(save_msg)
                }
                if data["error_infos"]:
                    data["error_infos"].append(save_error)
                else:
                    data["error_infos"] = [save_error]
        check_brief_info = app_check_service.wrap_service_check_info(self.service, data)
        code_from = self.service.code_from
        if code_from in support_oauth_type.keys():
            for i in check_brief_info["service_info"]:
                if i["type"] == "source_from":
                    result_url = re_spilt("[:,@]", i["value"])
                    if len(result_url) != 2:
                        i["value"] = result_url[0] + '//' + result_url[-2] + result_url[-1]
        result = general_message(200, "success", "请求成功", bean=check_brief_info)
        return Response(result, status=result["code"])

    @never_cache
    def post(self, request, *args, **kwargs):
        """
        组件信息检测
        ---
        parameters:
            - name: tenantName
              description: 租户名
              required: true
              type: string
              paramType: path
            - name: serviceAlias
              description: 组件别名
              required: true
              type: string
              paramType: path

        """
        user = request.user
        is_again = request.data.get("is_again", False)
        code, msg, service_info = app_check_service.check_service(self.tenant, self.service, is_again, user)
        if code != 200:
            result = general_message(code, "check service error", msg)
        else:
            result = general_message(200, "success", "操作成功", bean=service_info)
        return Response(result, status=result["code"])


class GetCheckUUID(AppBaseView):
    @never_cache
    def get(self, request, *args, **kwargs):
        result = general_message(200, u"success", "获取成功", bean={"check_uuid": self.service.check_uuid})
        return Response(result, status=200)


class AppCheckUpdate(AppBaseView):
    @never_cache
    def put(self, request, *args, **kwargs):
        """
        组件检测信息修改
        ---
        serializer: TenantServiceUpdateSerilizer
        """
        data = request.data

        serializer = TenantServiceUpdateSerilizer(data=data)
        if not serializer.is_valid():
            result = general_message(400, "{0}".format(serializer.errors), "参数异常")
            return Response(result, status=result["code"])
        params = dict(serializer.data)

        code, msg = app_service.update_check_app(self.tenant, self.service, params)
        if code != 200:
            return Response(general_message(code, "update service info error", msg), status=code)
        result = general_message(200, u"success", "修改成功")
        return Response(result, status=result["code"])
