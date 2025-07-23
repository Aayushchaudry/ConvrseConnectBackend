import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.review_items.controllers import router

# Check if the required endpoints are defined
endpoints = [route.path for route in router.routes]
required_endpoints = [
    "/api/v1/internal-tasks/{task_id}/complete-with-files",
    "/api/v1/review-items/{review_item_id}/files",
    "/api/v1/review-items/{review_item_id}/files/{file_id}/version"
]

print("Checking if required endpoints are defined:")
for endpoint in required_endpoints:
    if endpoint in endpoints:
        print(f"✅ {endpoint} is defined")
    else:
        print(f"❌ {endpoint} is NOT defined")

# Check if the required HTTP methods are defined
methods = {route.path: route.methods for route in router.routes}
required_methods = {
    "/api/v1/internal-tasks/{task_id}/complete-with-files": {"POST"},
    "/api/v1/review-items/{review_item_id}/files": {"GET"},
    "/api/v1/review-items/{review_item_id}/files/{file_id}/version": {"PUT"}
}

print("\nChecking if required HTTP methods are defined:")
for endpoint, required_method in required_methods.items():
    if endpoint in methods and required_method.issubset(methods[endpoint]):
        print(f"✅ {endpoint} supports {required_method}")
    else:
        print(f"❌ {endpoint} does NOT support {required_method}")