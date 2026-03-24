Redis Graph Connection Manager
==============================

Redis Graph Connection Manager is a Python module designed to efficiently manage and query domain-to-member
connection graphs using Redis as the backend.

In this documentation, when we say **connection** we mean an **edge connection** (a directed edge) between two nodes in
the graph.

It provides utilities for adding, removing, and versioning connections, supporting scalable and high-performance graph
operations that are essential for real-time communication platforms.

.. contents::
   :local:
   :depth: 2

Overview
--------

- Redis-backed connection graphs (outgoing and incoming) between domains and subjects.
- Consistent versioning of edges using Redis sorted sets and counters.
- Soft-delete support for outgoing edges to preserve history while removing them from the active graph.
- Helpers to page through active edge connections and inspect removed ones.

Features
--------

* Add single or multiple edge connections between a domain and subjects.
* Retrieve paginated active edge connections and all removed edge connections.
* Fetch all active edge connections for a domain.
* Compute intersections between connection graphs (edge connections).
* Maintain and query connection versions (edge versions).
* Soft-delete edge connections and remove entire domains.

Installation
------------

The package is published on PyPI as ``graphconnectionmanager``. Import it in Python as ``redisgraph``.

.. code-block:: bash

   pip install graphconnectionmanager-0.1.5-py3-none-any.whl

Quickstart
----------

.. code-block:: python

   from redisgraph import GraphManager
   import redis

   # Initialize Redis client and GraphManager
   redis_client = redis.Redis(host="localhost", port=6379, db=0)
   manager = GraphManager(redis_client, prefix="graph", namespace="phonebook")

   # Add a connection from domain 'user_1' to member '8801791223344'
   manager.add_connection("user_1", "8801791223344")

   # Retrieve all active connections for 'user_1'
   connections, removed, next_page = manager.get_connections("user_1")
   print(connections, removed, next_page)

Graph Data Structure and Algorithms
-----------------------------------

.. toctree::
   :maxdepth: 1

   graph_algorithms

API Reference
-------------

.. toctree::
   :maxdepth: 1

   api
