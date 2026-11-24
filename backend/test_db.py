import sys
sys.path.insert(0, '.')
from app.config import settings
s = settings()
print('DATABASE_URL set:', bool(s.database_url))
print('REDIS_URL set:', bool(s.redis_url))

# Now test actual connection
from app.db import connection
try:
    with connection() as conn:
        result = conn.execute('SELECT 1')
        print('Query result:', result.fetchone())
except Exception as e:
    print(f'Error type: {type(e).__name__}')
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()