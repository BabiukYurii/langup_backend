# Async consumer worker (Redis Streams consumer group): reads events via
# XREADGROUP, routes them to registered handlers, and XACKs on success.
