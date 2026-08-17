"""Running synchronous ORM code from Bolt's event loop.

Bolt will offload a *sync* handler to a worker thread by itself, but it decides
whether to by statically analysing the handler's own source for ORM patterns.
That analysis cannot see through a call into another module, so a handler whose
queries all happen inside services.py or a schema builder is read as
non-blocking and run straight on the event loop — where the first ORM call
raises SynchronousOnlyOperation.

Rather than depend on where the queries happen to be written, the handlers here
are async and hand their synchronous body to this function. It is the same
thing Django does for a sync view under ASGI, including the connection
housekeeping that request_started/request_finished would normally do (Bolt
leaves BOLT_EMIT_SIGNALS off, so those signals never fire).
"""
from asgiref.sync import sync_to_async
from django.db import close_old_connections


def _call(fn, args, kwargs):
    close_old_connections()
    try:
        return fn(*args, **kwargs)
    finally:
        close_old_connections()


async def run_db(fn, *args, **kwargs):
    """Await a synchronous, database-touching callable on a worker thread.

    thread_sensitive=False so requests run in parallel across asgiref's pool
    instead of queueing behind one shared thread. Django opens a connection per
    thread, which is safe, and SQLite serialises the writes underneath anyway.
    """
    return await sync_to_async(_call, thread_sensitive=False)(fn, args, kwargs)
