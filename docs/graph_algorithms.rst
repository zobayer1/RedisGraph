Graph Data Structure and Algorithms
===================================

This library implements a directed connection graph backed by Redis sorted sets (ZSETs). In this documentation,
**connection** refers to an **edge connection** (a directed edge). Each connection
between a *domain* (for example, a room, group, or user) and a *subject* (for example, a member or contact)
is represented as an edge in two complementary graphs:

* **Outgoing graph**: from domain to subject, meaning domain has subject as a member.
* **Incoming graph**: from subject to domain, meaning subject belongs to the domain.

For each domain and subject we maintain a monotonically increasing **version counter** and use the version
as the score in the corresponding sorted set entries.

Key Layout
----------

The exact key format is controlled by :class:`redisgraph.GraphManager`, via its ``prefix`` and
``namespace`` constructor arguments and the private ``_get_graph_key`` helper.

Conceptually, for a given ``domain_id`` and ``graph_type`` (``OUTGOING`` or ``INCOMING``), the keys are:

* Graph key:

  ``<prefix>:connection:<namespace>:<direction>:<domain_id>``

  where:

  * ``prefix`` is the top-level key prefix (for example, ``"graph"``).
  * ``namespace`` identifies the logical graph domain (for example, ``"group_user"``, ``"group"``, ``"phonebook"``).
  * ``direction`` is either ``"outgoing"`` or ``"incoming"`` (from :class:`redisgraph.GraphType`).

* Version key (for the same node and direction):

  ``<prefix>:connection:<namespace>:<direction>:<domain_id>:version``

Concretely, when you configure the manager as::

    from redisgraph import GraphManager
    import redis

    client = redis.Redis(host="localhost", port=6379, db=0)
    manager = GraphManager(client, prefix="graph", namespace="group_user")

* Outgoing edges for a specific group-user node::

    graph:connection:group_user:outgoing:1434723f-e1ec-4f93-b241-390449b2e87a

* Version for a specific outgoing group-user node::

    graph:connection:group_user:outgoing:1434723f-e1ec-4f93-b241-390449b2e87a:version

* Incoming edges for a specific group-user node::

    graph:connection:group_user:incoming:56c82d3a-d288-4195-a72f-be97a8ef02ad

* Version for a specific incoming group-user node::

    graph:connection:group_user:incoming:56c82d3a-d288-4195-a72f-be97a8ef02ad:version

These keys remain valid with the new constructor: as long as you pass ``prefix="graph"`` and the matching
``namespace`` (for example, ``"group_user"``), the manager will read and write data under these existing keys.

The ZSET maps neighbor IDs to scores:

* Positive scores represent **active** edge connections.
* Negative scores represent **soft-deleted** edge connections in either graph direction.

Add Connection
--------------

When adding a connection (edge connection) from a domain entity (for example, ``user1``) to a subject (for example,
``subject1``)::

   add_connection(domain, subject):
     1. Increment the domain's version counter to get ``dv``.
     2. Add ``subject1`` to the outgoing ZSET of ``user1`` with score ``dv``.
     3. Increment the subject's version counter to get ``sv``.
     4. Add ``user1`` to the incoming ZSET of ``subject1`` with score ``sv``.

This ensures that both outgoing and incoming relationships are tracked and versioned for efficient querying and
historical tracking, and that the connection graph (edge connections) is updated in both directions for existing
entries.

Remove Connection
-----------------

When removing a connection (edge connection) from a domain entity (for example, ``user1``) to a subject (for example,
``subject1``)::

   remove_connection(domain, subject, soft=True):
     1. Increment the domain's version counter to get ``dv``.
     2. Add ``subject1`` to the outgoing ZSET of ``user1`` with score ``-dv`` (soft delete).
     3. Increment the subject's incoming version counter to get ``sv``.
     4. Add ``user1`` to the incoming ZSET of ``subject1`` with score ``-sv`` (soft delete).

   remove_connection(domain, subject, soft=False):
     1. Remove ``subject1`` from the outgoing ZSET of ``user1`` entirely (hard delete).
     2. Remove ``user1`` from the incoming ZSET of ``subject1`` entirely (hard delete).

The default negative scores keep a historical marker of the removal in both directions while still excluding the edge
from active-connection queries.

Get Connections
---------------

To retrieve a paginated list of active edge connections and all removed (soft-deleted) edge connections for a given
domain::

   get_connections(domain_id, graph_type=OUTGOING, size=100, cut_off=0):
     # Fetch Active Connections
     - Query the ``graph_type`` ZSET for ``domain_id`` to fetch up to ``size`` items with positive scores
       in the range ``(cut_off, +inf]`` (exclusive lower bound).
     - Collect the list of active connection IDs and their scores.

     # Determine Score Range
     - If the active list is not empty, set ``max_score`` to the highest score among the fetched items.
     - If the active list is empty, set ``max_score`` to the current domain version value.

     # Fetch Removed Connections
     - Query the same ZSET for items with negative scores
       in the range ``[-max_score, -cut_off)`` (inclusive lower, exclusive upper bound).
     - Collect the list of removed (soft-deleted) connection IDs.

     # Return Results
     - Return the list of active connection IDs, the list of removed connection IDs, and the ``max_score`` value,
       which can be used as the new ``cut_off`` for the next page.

Only the active edge connections are paginated, while all removed edge connections within the score window are fetched in a
single call. The pagination order is ascending by score.

Intersection of Graphs
----------------------

To compute the intersection of two domains' outgoing graphs, the manager retrieves only entries with positive
scores from each domain's ZSET and computes the set intersection of their member IDs. Entries with negative
scores (soft-deleted edge connections) are excluded, so only currently active edge connections are considered.

Complexity Considerations
-------------------------

* Adding or removing a single edge connection is ``O(log N)`` per affected ZSET.
* Paginating active edge connections uses standard ZSET range queries and is efficient even for large graphs.
* Soft deletes keep the historical markers in both graph directions; periodic cleanup can be implemented
  externally if old negative entries are no longer needed.

For concrete usage examples, see :class:`redisgraph.GraphManager` and the unit tests in
``tests/test_graph_manager.py``.
