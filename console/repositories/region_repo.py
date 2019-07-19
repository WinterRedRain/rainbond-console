# -*- coding: utf-8 -*-
from backends.models import RegionConfig
from console.repositories.team_repo import team_repo
from www.models.main import TenantRegionInfo


class RegionRepo(object):
    def get_active_region_by_tenant_name(self, tenant_name):
        tenant = team_repo.get_tenant_by_tenant_name(tenant_name=tenant_name, exception=True)
        regions = TenantRegionInfo.objects.filter(tenant_id=tenant.tenant_id, is_active=1, is_init=1)
        if regions:
            return regions
        return None

    def get_region_by_tenant_name(self, tenant_name):
        tenant = team_repo.get_tenant_by_tenant_name(tenant_name=tenant_name, exception=True)
        regions = TenantRegionInfo.objects.filter(tenant_id=tenant.tenant_id)
        if regions:
            return regions
        return None

    def get_region_by_region_id(self, region_id):
        regions = TenantRegionInfo.objects.filter(region_id=region_id)
        if regions and len(regions) > 0:
            return regions[0]
        return None

    def get_region_desc_by_region_name(self, region_name):
        regions = RegionConfig.objects.filter(region_name=region_name)
        if regions:
            region_desc = regions[0].desc
            return region_desc
        else:
            return None

    def get_usable_regions(self):
        """获取可使用的数据中心"""
        usable_regions = RegionConfig.objects.filter(status="1")
        return usable_regions

    def get_team_opened_region(self, team_name):
        """获取团队已开通的数据中心"""
        tenant = team_repo.get_team_by_team_name(team_name)
        return TenantRegionInfo.objects.filter(tenant_id=tenant.tenant_id)

    def get_region_by_region_name(self, region_name):
        region_configs = RegionConfig.objects.filter(region_name=region_name)
        if region_configs:
            return region_configs[0]
        return None

    def get_region_by_region_names(self, region_names):
        return RegionConfig.objects.filter(region_name__in=region_names)

    def get_team_region_by_tenant_and_region(self, tenant_id, region):
        tenant_regions = TenantRegionInfo.objects.filter(tenant_id=tenant_id, region_name=region)
        if tenant_regions:
            return tenant_regions[0]
        return None

    def create_tenant_region(self, **params):
        return TenantRegionInfo.objects.create(**params)

    def create_region(self, region_data):
        region_config = RegionConfig(**region_data)
        region_config.save()
        return region_config

    def update_region(self, region):
        region.save()
        return region

    def get_all_regions(self):
        return RegionConfig.objects.all()

    def get_regions_by_tenant_ids(self, tenant_ids):
        return TenantRegionInfo.objects.filter(tenant_id__in=tenant_ids, is_init=True).values_list("region_name", flat=True)

    def get_region_info_by_region_name(self, region_name):
        return RegionConfig.objects.filter(region_name=region_name)


region_repo = RegionRepo()
