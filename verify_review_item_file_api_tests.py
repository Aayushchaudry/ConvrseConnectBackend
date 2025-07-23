import sys
from pathlib import Path
import inspect

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Import the test module
from tests.integration.test_review_item_file_api import (
    test_complete_task_with_files,
    test_get_review_item_files,
    test_create_file_version
)

# Check if the required test functions are defined
required_tests = [
    "test_complete_task_with_files",
    "test_get_review_item_files",
    "test_create_file_version"
]

print("Checking if required test functions are defined:")
for test_name in required_tests:
    if test_name in globals():
        print(f"✅ {test_name} is defined")
    else:
        print(f"❌ {test_name} is NOT defined")

# Check if the test functions have the correct parameters
required_params = {
    "test_complete_task_with_files": ["db_session", "test_client", "mock_auth_middleware", "mock_file_upload_service"],
    "test_get_review_item_files": ["db_session", "test_client", "mock_auth_middleware"],
    "test_create_file_version": ["db_session", "test_client", "mock_auth_middleware", "mock_file_upload_service"]
}

print("\nChecking if test functions have the correct parameters:")
for test_name, params in required_params.items():
    if test_name in globals():
        test_func = globals()[test_name]
        sig = inspect.signature(test_func)
        actual_params = list(sig.parameters.keys())
        if all(param in actual_params for param in params):
            print(f"✅ {test_name} has the correct parameters")
        else:
            print(f"❌ {test_name} is missing some parameters: expected {params}, got {actual_params}")
    else:
        print(f"❌ {test_name} is not defined")