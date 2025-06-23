# Review Item File Reference Improvements

## Overview

Updated the ReviewItem model and related services to properly handle file references instead of using hardcoded placeholder URLs. This enables better integration with platform-service and supports review items that don't require file attachments.

## Changes Made

### 1. Database Schema Updates

**Migration**: `update_review_item_file_references_20241223.sql`

- ✅ **Added `platform_file_id` column** (UUID, nullable) - References files stored in platform-service
- ✅ **Made `item_url` nullable** - Some review items may not need file attachments (e.g., approval-only items)
- ✅ **Added database index** on `platform_file_id` for performance
- ✅ **Added descriptive comments** for both columns

### 2. Enum Fixes

**Migrations**: 
- `add_review_item_enum_values_20241223.sql`
- `add_review_status_enum_values_20241223.sql` 
- `cleanup_enum_values_20241223.sql`

- ✅ **Fixed ReviewItemType enum** - Added missing business-specific values:
  - `STATIC_RENDER` - For modeling/static image reviews
  - `TEXTURE_REVIEW` - For texture and material reviews
  - `FINAL_RENDER` - For final rendering reviews
  - `WORK_REVIEW` - For general work completion reviews

- ✅ **Fixed ReviewStatus enum** - Added uppercase versions:
  - `PENDING_REVIEW` - Waiting for client to review
  - `APPROVED` - Client has approved this item
  - `REJECTED` - Client has rejected this item
  - `NEEDS_REVISION` - Client has provided comments requiring revisions

- ✅ **Cleaned up unnecessary lowercase enum values** from database

### 3. Model Updates

**File**: `src/models/review_item.py`

```python
# File reference options - either platform_file_id OR item_url can be used
platform_file_id = Column(
    UUID(as_uuid=True), nullable=True
)  # Reference to file ID in platform-service for review assets
item_url = Column(
    Text, nullable=True
)  # Optional URL to the asset - nullable for review items that do not require file attachments
```

### 4. Service Logic Updates

**File**: `src/services/review_management_service.py`

- ✅ **Removed hardcoded placeholder URLs** (`"http://example.com/placeholder.jpg"`)
- ✅ **Added support for `platform_file_id`** in review item creation
- ✅ **Made `item_url` properly nullable** - defaults to None instead of placeholder

### 5. Command Updates

**File**: `src/orchestrators/deliverable_saga_orchestrator/commands.py`

```python
@dataclass
class GenerateReviewItemCommand(BaseCommand):
    project_id: UUID
    deliverable_id: UUID
    review_item_type: str
    asset_urls: List[str]  # URLs to the assets (optional, for backwards compatibility)
    platform_file_id: Optional[UUID]  # Reference to file ID in platform-service
```

## Usage

### For Review Items with File Attachments

```python
# Using platform-service file reference (preferred)
command = GenerateReviewItemCommand(
    project_id=project_id,
    deliverable_id=deliverable_id,
    review_item_type="STATIC_RENDER",
    platform_file_id=uuid.UUID("some-file-id-from-platform-service")
)

# Using direct URL (backwards compatibility)
command = GenerateReviewItemCommand(
    project_id=project_id,
    deliverable_id=deliverable_id,
    review_item_type="STATIC_RENDER",
    asset_urls=["https://example.com/asset.jpg"]
)
```

### For Review Items without File Attachments

```python
# Approval-only review item (no files needed)
command = GenerateReviewItemCommand(
    project_id=project_id,
    deliverable_id=deliverable_id,
    review_item_type="WORK_REVIEW"
    # Both platform_file_id and asset_urls are None/empty
)
```

## Database Schema

```sql
-- Review items table structure
connect_backend.review_items
├── id (UUID, PK)
├── deliverable_id (UUID, FK)
├── project_id (UUID, FK)
├── source_internal_task_id (UUID, FK)
├── item_type (ReviewItemType enum)
├── platform_file_id (UUID, nullable) -- NEW: Reference to platform-service file
├── item_url (Text, nullable) -- UPDATED: Now nullable, no more hardcoded URLs
├── description (Text, nullable)
├── review_status (ReviewStatus enum)
├── sequence_number (Integer, nullable)
├── review_round (Integer, nullable)
├── presented_at (DateTime)
├── created_at (DateTime)
└── updated_at (DateTime)
```

## Benefits

1. **No more hardcoded URLs** - Eliminates placeholder URLs that don't work
2. **Proper file integration** - References actual files stored in platform-service
3. **Flexible file handling** - Supports both file-based and approval-only review items
4. **Consistent enum values** - Fixes enum mismatches that caused database errors
5. **Better performance** - Database index on platform_file_id for faster lookups
6. **Backwards compatibility** - Still supports asset_urls for existing workflows

## Next Steps

- Update frontend to use `platform_file_id` when available
- Implement platform-service integration for file uploads during task completion
- Add validation to ensure either `platform_file_id` OR `item_url` is provided when files are needed
- Consider adding file metadata caching for better performance 