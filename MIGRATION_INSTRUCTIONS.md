# Migration Instructions for Status Field

## Migration File Created

The migration file `20251109_07_add_status_to_trades.py` has been created and is ready to apply.

**Location**: `migrations/versions/20251109_07_add_status_to_trades.py`

**What it does**:
1. Adds `status` column (String(32), nullable) to `trades` table
2. Populates existing records:
   - Sets `status = 'OPEN'` if `closed_at IS NULL`
   - Sets `status = 'CLOSED'` if `closed_at IS NOT NULL`

**Migration Chain**:
- Revision: `20251109_07_status_trades`
- Down Revision: `20251109_06_user_settings` (correctly linked)

## To Apply the Migration

### Option 1: Using Alembic Directly (Recommended)

```bash
cd OfficialTBot-api

# Make sure you have alembic installed
pip install alembic

# Or if using a virtual environment:
# source venv/bin/activate  # or your venv path
# pip install -r requirements.txt

# Check current migration state
alembic current

# Apply all pending migrations
alembic upgrade head
```

### Option 2: Using Make (if available)

```bash
cd OfficialTBot-api
make migrate
```

### Option 3: Using Python Script

```bash
cd OfficialTBot-api

# Install dependencies first
pip install alembic sqlalchemy

# Run the migration script
python3 apply_migration.py
```

## Verification

After running the migration, verify it was applied:

```bash
# Check current migration state
alembic current

# Should show: 20251109_07_status_trades (head)
```

You can also verify in your database:

```sql
-- Check if status column exists
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'trades' AND column_name = 'status';

-- Check if status values were populated
SELECT status, COUNT(*) 
FROM trades 
GROUP BY status;
```

## Rollback (if needed)

If you need to rollback the migration:

```bash
alembic downgrade -1
```

This will remove the `status` column from the `trades` table.

## Notes

- The migration is **backwards compatible** - existing code that infers status from `closed_at` will continue to work
- The migration populates the status field for all existing trades
- New trades will have status set by the application code (see `app/internal.py`)

