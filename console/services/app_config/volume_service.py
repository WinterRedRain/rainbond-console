# -*- coding: utf8 -*-
"""
  Created on 18/1/17.
"""
import re

from console.constants import AppConstants
from console.repositories.app_config import volume_repo, mnt_repo

from www.apiclient.regionapi import RegionInvokeApi
import logging
from console.utils.urlutil import is_path_legal
from www.utils.crypt import make_uuid

region_api = RegionInvokeApi()
logger = logging.getLogger("default")


class AppVolumeService(object):
    SYSDIRS = [
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/home",
        "/lib",
        "/lib64",
        "/opt",
        "/proc",
        "/root",
        "/sbin",
        "/srv",
        "/sys",
        "/tmp",
        "/usr",
        "/var",
        "/usr/local",
        "/usr/sbin",
        "/usr/bin",
    ]

    def get_service_support_volume_providers(self, tenant, service, kind=''):
        res, body = region_api.get_volume_providers(service.service_region, tenant.tenant_name, kind)
        # 过滤share-file & local-file的StorageClass
        if res.status != 200:
            return 200, []
        return 200, body.list

    # 需要提供更多的信息到源数据中
    # 使用数据中心接口统一返回最合适的类型，
    def get_best_suitable_volume_settings(self, tenant, service, volume_type, access_mode=None, share_policy=None,
                                          backup_policy=None, reclaim_policy=None, provider_name=None):
        data = {
            "volume_type": volume_type,
            "access_mode": access_mode,
            "share_policy": share_policy,
            "backup_policy": backup_policy
            }
        """
        settings 结构
        volume_type: string 新的存储类型，没有合适的相同的存储则返回新的存储
        changed: bool 是否有合适的相同的存储
        ... 后续待补充
        """
        settings = region_api.get_volume_best_selector(service.service_region, tenant.tenant_name, data)
        return settings.bean

    def get_service_volumes(self, tenant, service, is_config_file):
        volumes = []
        if is_config_file:
            volumes = volume_repo.get_service_volumes_about_config_file(service.service_id)
        else:
            volumes = volume_repo.get_service_volumes(service.service_id)
        vos = []
        res = None
        body = None
        try:
            res, body = region_api.get_service_volumes_status(service.service_region, tenant.tenant_name, service.service_alias)
        except Exception as e:
            logger.exception(e)
        if res is None or (res is not None and res.status != 200):
            for volume in volumes:
                vo = volume.to_dict()
                vo["status"] = 'unknown'  # 与后端的未绑定进行统一
                vos.append(vo)
            return vos
        if body and body.bean:
            for volume in volumes:
                vo = volume.to_dict()
                if vo["volume_name"] in body.bean.status:
                    vo["status"] = body.bean.status[vo["volume_name"]]
                else:
                    vo["status"] = 'unknown'
                vos.append(vo)
        return vos

    def check_volume_name(self, service, volume_name):
        r = re.compile(u'^[a-zA-Z0-9_]+$')
        if not r.match(volume_name):
            if service.service_source != AppConstants.MARKET:
                return 400, u"持久化名称只支持数字字母下划线", volume_name
            else:
                volume_name = service.service_cname + make_uuid()[-3:]
        volume = volume_repo.get_service_volume_by_name(
            service.service_id, volume_name)

        if volume:
            return 412, u"持久化名称{0}已存在".format(volume_name), volume_name
        else:
            return 200, u"success", volume_name

    def check_volume_path(self, service, volume_path, local_path):
        if local_path:
            for path in local_path:
                # if volume_path.startswith(path):
                #     return 412, u"持久化路径不能和挂载共享路径相同"
                if volume_path.startswith(path + "/"):
                    return 412, u"持久化路径不能再挂载共享路径下"
        volume = volume_repo.get_service_volume_by_path(
            service.service_id, volume_path)
        if volume:
            return 412, u"持久化路径 {0} 已存在".format(volume_path)
        if service.service_source == AppConstants.SOURCE_CODE:
            if volume_path == "/app":
                return 409, u"源码组件不能挂载/app目录"
        if service.image != "goodrain.me/runner":
            volume_path_win = False
            if re.match('[a-zA-Z]', volume_path[0]) and volume_path[1] == ':':
                volume_path_win = True
            if not volume_path.startswith("/") and not volume_path_win:
                return 400, u"路径仅支持linux和windows"
            if volume_path in self.SYSDIRS:
                return 412, u"路径{0}为系统路径".format(volume_path)
            if volume_path_win and len(volume_path) == 3:
                return 412, u"路径不能为系统路径"
        else:
            if not is_path_legal(volume_path):
                return 412, u"请输入符合规范的路径（如：/app/volumes ）"
        all_volumes = volume_repo.get_service_volumes(
            service.service_id).values("volume_path")
        for path in list(all_volumes):
            # volume_path不能重复

            if path["volume_path"].startswith(volume_path + "/"):
                return 412, u"已存在以{0}开头的路径".format(path["volume_path"])
            if volume_path.startswith(path["volume_path"] + "/"):
                return 412, u"已存在以{0}开头的路径".format(volume_path)

        return 200, u"success"

    def add_service_volume(self, tenant, service, volume_path, volume_type, volume_name, file_content=None, settings=None):
        volume_name = volume_name.strip()
        volume_path = volume_path.strip()
        code, msg, volume_name = self.check_volume_name(service, volume_name)
        dep_mnt_names = mnt_repo.get_service_mnts(
            tenant.tenant_id, service.service_id).values_list('mnt_dir',
                                                              flat=True)
        local_path = []
        if dep_mnt_names:
            local_path.append(
                dep_mnt_names.values("mnt_dir")[0].get("mnt_dir"))
        if code != 200:
            return code, msg, None
        code, msg = self.check_volume_path(service, volume_path, local_path)
        if code != 200:
            return code, msg, None
        host_path = "/grdata/tenant/{0}/service/{1}{2}".format(
            tenant.tenant_id, service.service_id, volume_path)
        volume_data = {
            "service_id": service.service_id,
            "category": service.category,
            "host_path": host_path,
            "volume_type": volume_type,
            "volume_path": volume_path,
            "volume_name": volume_name
        }
        if settings:
            volume_data['volume_capacity'] = settings['volume_capacity']
            volume_data['volume_provider_name'] = settings['provider_name']
            volume_data['access_mode'] = settings['access_mode']
            volume_data['share_policy'] = settings['share_policy']
            volume_data['backup_policy'] = settings['backup_policy']
            volume_data['reclaim_policy'] = settings['reclaim_policy']
            volume_data['allow_expansion'] = settings['allow_expansion']
        # region端添加数据
        if service.create_status == "complete":
            if volume_type == "config-file":
                data = {
                    "category": service.category,
                    "volume_name": volume_name,
                    "volume_path": volume_path,
                    "volume_type": volume_type,
                    "file_content": file_content,
                    "enterprise_id": tenant.enterprise_id
                }
            else:
                data = {
                    "category": service.category,
                    "volume_name": volume_name,
                    "volume_path": volume_path,
                    "volume_type": volume_type,
                    "enterprise_id": tenant.enterprise_id
                }
            if settings:
                data['volume_capacity'] = settings['volume_capacity']
                data['volume_provider_name'] = settings['provider_name']
                data['access_mode'] = settings['access_mode']
                data['share_policy'] = settings['share_policy']
                data['backup_policy'] = settings['backup_policy']
                data['reclaim_policy'] = settings['reclaim_policy']
                data['allow_expansion'] = settings['allow_expansion']
            res, body = region_api.add_service_volumes(service.service_region, tenant.tenant_name, service.service_alias, data)
            logger.debug(body)

        volume = volume_repo.add_service_volume(**volume_data)
        if volume_type == "config-file":
            file_data = {
                "service_id": service.service_id,
                "volume_id": volume.ID,
                "file_content": file_content
            }
            volume_repo.add_service_config_file(**file_data)
        return 200, "success", volume

    def delete_service_volume_by_id(self, tenant, service, volume_id):
        volume = volume_repo.get_service_volume_by_pk(volume_id)
        if not volume:
            return 404, u"需要删除的路径不存在", None
        # if volume.volume_type == volume.SHARE:
        # 判断当前共享目录是否被使用
        mnt = mnt_repo.get_mnt_by_dep_id_and_mntname(service.service_id,
                                                     volume.volume_name)
        if mnt:
            return 403, u"当前路径被共享,无法删除", None
        if service.create_status == "complete":
            res, body = region_api.delete_service_volumes(
                service.service_region, tenant.tenant_name,
                service.service_alias, volume.volume_name,
                tenant.enterprise_id)
            logger.debug("service {0} delete volume {1}, result {2}".format(
                service.service_cname, volume.volume_name, body))

        volume_repo.delete_volume_by_id(volume_id)
        volume_repo.delete_file_by_volume_id(volume_id)

        return 200, u"success", volume

    def delete_service_volumes(self, service):
        volume_repo.delete_service_volumes(service.service_id)

    def delete_region_volumes(self, tenant, service):
        volumes = volume_repo.get_service_volumes(service.service_id)
        for volume in volumes:
            try:
                res, body = region_api.delete_service_volumes(
                    service.service_region, tenant.tenant_name,
                    service.service_alias, volume.volume_name,
                    tenant.enterprise_id)
            except Exception as e:
                logger.exception(e)
