from stark.service.stark import site, ModelStark
from .models import *


site.register(User)
site.register(Role)


class PerConfig(ModelStark):
    list_display = ["id", "title", "url", "group", "action"]


site.register(Permission, PerConfig)
site.register(PermissionGroup)
