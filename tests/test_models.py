"""
Test models import and metadata inspection
Verification script for Subphase 1.3
"""
from app.models import Base, Tenant, User, UserRole, TenantMixin, TimestampMixin


def test_model_imports():
    """Test that all models can be imported successfully."""
    print("Testing model imports...")

    # Check Base
    assert Base is not None
    print("[PASS] Base model imported")

    # Check Mixins
    assert TenantMixin is not None
    assert TimestampMixin is not None
    print("[PASS] Mixins imported")

    # Check Models
    assert Tenant is not None
    assert User is not None
    print("[PASS] Tenant and User models imported")

    # Check Enums
    assert UserRole is not None
    assert UserRole.TENANT_USER == "tenant_user"
    assert UserRole.PROPERTY_ADMIN == "property_admin"
    assert UserRole.SUPER_ADMIN == "super_admin"
    print("[PASS] UserRole enum imported and validated")


def test_metadata_inspection():
    """Inspect SQLAlchemy metadata to verify tables are registered."""
    print("\nInspecting SQLAlchemy metadata...")

    metadata = Base.metadata
    tables = metadata.tables

    print(f"[INFO] Registered tables: {list(tables.keys())}")

    # Check tables exist
    assert "users" in tables
    assert "tenants" in tables
    print("[PASS] Both tables registered in metadata")

    # Inspect User table
    users_table = tables["users"]
    user_columns = [col.name for col in users_table.columns]
    print(f"[INFO] Users table columns: {user_columns}")

    # Verify key columns
    required_user_cols = ["id", "tenant_id", "email", "role", "created_at", "updated_at"]
    for col in required_user_cols:
        assert col in user_columns, f"Missing column: {col}"
    print("[PASS] User table has all required columns")

    # Inspect Tenant table
    tenants_table = tables["tenants"]
    tenant_columns = [col.name for col in tenants_table.columns]
    print(f"[INFO] Tenants table columns: {tenant_columns}")

    # Verify key columns
    required_tenant_cols = ["id", "name", "slug", "created_at", "updated_at"]
    for col in required_tenant_cols:
        assert col in tenant_columns, f"Missing column: {col}"
    print("[PASS] Tenant table has all required columns")


def test_model_attributes():
    """Test that models have expected attributes and methods."""
    print("\nTesting model attributes...")

    # Test User model
    user_attrs = dir(User)
    assert "id" in user_attrs
    assert "tenant_id" in user_attrs
    assert "email" in user_attrs
    assert "role" in user_attrs
    print("[PASS] User model has expected attributes")

    # Test Tenant model
    tenant_attrs = dir(Tenant)
    assert "id" in tenant_attrs
    assert "name" in tenant_attrs
    assert "slug" in tenant_attrs
    print("[PASS] Tenant model has expected attributes")


if __name__ == "__main__":
    test_model_imports()
    test_metadata_inspection()
    test_model_attributes()
    print("\n[SUCCESS] All model tests passed!")
