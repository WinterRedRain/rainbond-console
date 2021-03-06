# -*- coding: utf8 -*-
"""
  Created on 18/3/15.
"""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response

from console.exception.main import AbortRequest
from console.services.config_service import EnterpriseConfigService
from console.services.config_service import ConfigService
from console.services.enterprise_services import enterprise_services
from console.utils.reqparse import bool_argument
from console.utils.reqparse import parse_item
from console.views.base import EnterpriseAdminView
from console.enum.system_config import ConfigKeyEnum

logger = logging.getLogger("default")


class EnterpriseConfigView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        title = parse_item(request, "title")
        logo = parse_item(request, "logo")
        favicon = parse_item(request, "favicon")
        enterprise_alias = parse_item(request, "enterprise_alias")

        config_service = ConfigService()
        if title:
            config_service.update_config_value(ConfigKeyEnum.TITLE.name, title)
        if logo:
            config_service.update_config_value(ConfigKeyEnum.LOGO.name, logo)
        if enterprise_alias:
            enterprise_services.update_alias(enterprise_id, enterprise_alias)
        if favicon:
            config_service.update_config_value(ConfigKeyEnum.FAVICON.name, favicon)

        return Response(status=status.HTTP_200_OK)


class EnterpriseObjectStorageView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        enable = bool_argument(parse_item(request, "enable", required=True))
        provider = parse_item(request, "provider", required=True)
        endpoint = parse_item(request, "endpoint", required=True)
        bucket_name = parse_item(request, "bucket_name", required=True)
        access_key = parse_item(request, "access_key", required=True)
        secret_key = parse_item(request, "secret_key", required=True)

        if provider not in ("alioss", "s3"):
            raise AbortRequest("provider {} not in (\"alioss\", \"s3\")".format(provider))

        ent_cfg_svc = EnterpriseConfigService(enterprise_id)
        ent_cfg_svc.update_config_enable_status(key="OBJECT_STORAGE", enable=enable)
        ent_cfg_svc.update_config_value(
            key="OBJECT_STORAGE",
            value={
                "provider": provider,
                "endpoint": endpoint,
                "bucket_name": bucket_name,
                "access_key": access_key,
                "secret_key": secret_key,
            })
        return Response(status=status.HTTP_200_OK)


class EnterpriseAppStoreImageHubView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        enable = bool_argument(parse_item(request, "enable", required=True))
        hub_url = parse_item(request, "hub_url", required=True)
        namespace = parse_item(request, "namespace")
        hub_user = parse_item(request, "hub_user")
        hub_password = parse_item(request, "hub_password")

        ent_cfg_svc = EnterpriseConfigService(enterprise_id)
        ent_cfg_svc.update_config_enable_status(key="APPSTORE_IMAGE_HUB", enable=enable)
        ent_cfg_svc.update_config_value(
            key="APPSTORE_IMAGE_HUB",
            value={
                "hub_url": hub_url,
                "namespace": namespace,
                "hub_user": hub_user,
                "hub_password": hub_password,
            })
        return Response(status=status.HTTP_200_OK)
