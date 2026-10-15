import warnings
from django.apps import AppConfig
from django.db.utils import OperationalError, InterfaceError


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'

    def ready(self):
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', 'Accessing the database during app initialization')
            try:
                from inventory.services import init_supplies
                init_supplies()
            except (OperationalError, InterfaceError):
                pass
            except Exception:
                pass
