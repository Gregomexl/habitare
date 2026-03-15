"""
Test models import and metadata inspection
Verification script for Subphase 1.3
"""
import pytest
from app.models import Base, Tenant, User, UserRole, TenantMixin, TimestampMixin


@pytest.mark.parametrize("model_class,expected_name", [
    (Base, "Base"),
    (TenantMixin, "TenantMixin"),
    (TimestampMixin, "TimestampMixin"),
    (Tenant, "Tenant"),
    (User, "User"),
    (UserRole, "UserRole"),
])
def test_model_imports(model_class, expected_name):
    """Test that all models can be imported successfully."""
    assert model_class is not None, f"{expected_name} should be importable"
    assert model_class.__name__ == expected_name


@pytest.mark.parametrize("role,expected_value", [
    (UserRole.TENANT_USER, "tenant_user"),
    (UserRole.PROPERTY_ADMIN, "property_admin"),
    (UserRole.SUPER_ADMIN, "super_admin"),
])
def test_user_role_enum(role, expected_value):
    """Test UserRole enum values."""
    assert role == expected_value


@pytest.mark.parametrize("table_name", ["users", "tenants"])
def test_tables_registered(table_name):
    """Test that tables are registered in SQLAlchemy metadata."""
    metadata = Base.metadata
    assert table_name in metadata.tables, f"Table '{table_name}' should be registered"


@pytest.mark.parametrize("column_name", [
    "id", "tenant_id", "email", "role", "created_at", "updated_at"
])
def test_user_table_columns(column_name):
    """Test User table has required columns."""
    users_table = Base.metadata.tables["users"]
    user_columns = [col.name for col in users_table.columns]
    assert column_name in user_columns, f"User table should have '{column_name}' column"


@pytest.mark.parametrize("column_name", [
    "id", "name", "slug", "created_at", "updated_at"
])
def test_tenant_table_columns(column_name):
    """Test Tenant table has required columns."""
    tenants_table = Base.metadata.tables["tenants"]
    tenant_columns = [col.name for col in tenants_table.columns]
    assert column_name in tenant_columns, f"Tenant table should have '{column_name}' column"


@pytest.mark.parametrize("model_class,attributes", [
    (User, ["id", "tenant_id", "email", "role"]),
    (Tenant, ["id", "name", "slug"]),
])
def test_model_attributes(model_class, attributes):
    """Test that models have expected attributes."""
    model_attrs = dir(model_class)
    for attr in attributes:
        assert attr in model_attrs, f"{model_class.__name__} should have '{attr}' attribute"
