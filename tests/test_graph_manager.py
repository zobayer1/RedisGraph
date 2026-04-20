from redis import Redis

from redisgraph import GraphManager, GraphType


def test_add_connection(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that a connection is added correctly.

    Pass criteria:
    - The outgoing and incoming connection scores are set to 1 in Redis.
    - The version keys for both domain and subject are set to 1.
    """
    domain_id = "domain123"
    subject_id = "subject456"

    # Add connection
    graph_manager.add_connection(domain_id, subject_id)

    # Check outgoing connection
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert 1 == int(redis_client.zscore(gkey, subject_id))
    assert 1 == int(redis_client.get(vgkey))

    # Check incoming connection
    rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
    assert 1 == int(redis_client.zscore(rkey, domain_id))
    assert 1 == int(redis_client.get(vrkey))

    # Clean up
    redis_client.delete(gkey, vgkey, rkey, vrkey)


def test_add_connection_list(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that multiple connections are added correctly.

    Pass criteria:
    - Outgoing connection scores for each subject are incremented as expected.
    - The version key for the domain reflects the number of connections.
    - Incoming connection scores and version keys for each subject are set to 1.
    """
    domain_id = "domain123"
    subject_ids = ["subject456", "subject789"]

    # Add multiple connections
    graph_manager.add_connection_list(domain_id, subject_ids)

    # Check outgoing connections
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert 1 == int(redis_client.zscore(gkey, subject_ids[0]))
    assert 2 == int(redis_client.zscore(gkey, subject_ids[1]))
    assert 2 == int(redis_client.get(vgkey))

    # Check incoming connections
    rkey0, vrkey0 = graph_manager._get_graph_key(subject_ids[0], graph_type=GraphType.INCOMING)
    assert 1 == int(redis_client.zscore(rkey0, domain_id))
    assert 1 == int(redis_client.get(vrkey0))
    rkey1, vrkey1 = graph_manager._get_graph_key(subject_ids[1], graph_type=GraphType.INCOMING)
    assert 1 == int(redis_client.zscore(rkey1, domain_id))
    assert 1 == int(redis_client.get(vrkey1))

    # Clean up
    redis_client.delete(gkey, vgkey, rkey0, vrkey0, rkey1, vrkey1)


def test_get_all_connections(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that all connections for a domain are retrieved correctly.

    Pass criteria:
    - The outgoing connections list contains all active subjects connected to the domain.
    """
    domain_id = "domain123"
    subject_ids = ["subject456", "subject789", "subject101"]

    # Add multiple connections
    graph_manager.add_connection_list(domain_id, subject_ids)

    # Remove some connections
    graph_manager.remove_connection(domain_id, subject_ids[0])

    subjects = graph_manager.get_all_connections(domain_id)
    assert set(subjects) == {"subject789", "subject101"}

    # Clean up
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    redis_client.delete(gkey, vgkey)
    for subject_id in subject_ids:
        rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)


def test_get_connections(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that paginated active and removed connections are retrieved correctly.

    Pass criteria:
    - An active connections list contains only non-removed subjects.
    - A removed connections list contains only removed subjects.
    - The max_score matches the number of connection operations performed.
    """
    # Add 5 connections
    domain_id = "domain123"
    subjects = ["subject0", "subject1", "subject2", "subject3", "subject4"]
    graph_manager.add_connection_list(domain_id, subjects)

    # Remove 2 connections
    graph_manager.remove_connection(domain_id, "subject0")
    graph_manager.remove_connection(domain_id, "subject1")

    # Get connections with cut_off=0, size=5 (should get top 3 actives)
    active, removed, max_score = graph_manager.get_connections(domain_id, cut_off=0, size=5)
    assert set(active) == {"subject2", "subject3", "subject4"}
    assert len(removed) == 0

    # Check from max_score and get removed connections
    active, removed, max_score = graph_manager.get_connections(domain_id, cut_off=max_score, size=5)
    assert len(active) == 0
    assert set(removed) == {"subject0", "subject1"}

    # Check max_score corresponds to the number of operations
    assert max_score == 7

    # Clean up
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    redis_client.delete(gkey, vgkey)
    for subject in subjects:
        rkey, vrkey = graph_manager._get_graph_key(subject, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)


def test_get_connections_returns_empty_when_version_key_missing(
    graph_manager: GraphManager, redis_client: Redis
) -> None:
    """get_connections() should early-return when the version key isn't initialized.

    Pass criteria:
    - If the `<graph>:version` key is missing/None, returns ([], [], 0).
    - This holds even if the graph ZSET contains members (defensive behavior).
    """
    domain_id = "domain123"
    subjects = ["subject0", "subject1"]

    # Create a graph with data.
    graph_manager.add_connection_list(domain_id, subjects)

    # Delete ONLY the version key to simulate an uninitialized/corrupt state.
    gkey, vkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert redis_client.exists(gkey) == 1
    redis_client.delete(vkey)
    assert redis_client.get(vkey) is None

    active, removed, max_score = graph_manager.get_connections(domain_id, cut_off=0, size=100)

    assert active == []
    assert removed == []
    assert max_score == 0

    # Clean up
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    redis_client.delete(gkey, vgkey)
    for subject in subjects:
        rkey, vrkey = graph_manager._get_graph_key(subject, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)


def test_get_latest_connections(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that the latest active connections are retrieved correctly.

    Pass criteria:
    - The latest connections list contains the most recently added active subjects.
    """
    # Add 5 connections
    domain_id = "domain123"
    subjects = ["subject0", "subject1", "subject2", "subject3", "subject4"]
    graph_manager.add_connection_list(domain_id, subjects)

    # Remove 2 connections
    graph_manager.remove_connection(domain_id, "subject0")
    graph_manager.remove_connection(domain_id, "subject1")

    latest_connections = graph_manager.get_latest_connections(domain_id, size=3)
    assert latest_connections == ["subject4", "subject3", "subject2"]

    # Clean up
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    redis_client.delete(gkey, vgkey)
    for subject in subjects:
        rkey, vrkey = graph_manager._get_graph_key(subject, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)


def test_get_intersection(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that the intersection of two domains is retrieved correctly.

    Pass criteria:
    - The intersection contains only subjects present in both domains' outgoing connections.
    """
    domain_left = "domain123"
    domain_right = "domain456"

    # Add connections to both domains
    graph_manager.add_connection_list(domain_left, ["subject1", "subject2", "subject_removed"])
    graph_manager.add_connection_list(domain_right, ["subject2", "subject3", "subject_removed"])
    # Mark subject_removed as inactive on the right to ensure negative-score entries are filtered out
    graph_manager.remove_connection(domain_right, "subject_removed")

    # Get intersection
    intersection = graph_manager.get_intersection(domain_left, domain_right, graph_type=GraphType.OUTGOING)

    assert set(intersection) == {"subject2"}

    # Clean up
    gkey_left, vgkey_left = graph_manager._get_graph_key(domain_left, graph_type=GraphType.OUTGOING)
    gkey_right, vgkey_right = graph_manager._get_graph_key(domain_right, graph_type=GraphType.OUTGOING)
    redis_client.delete(gkey_left, vgkey_left, gkey_right, vgkey_right)
    for subject_id in ["subject1", "subject2", "subject3", "subject_removed"]:
        rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)


def test_get_version(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that the version of a connection is retrieved correctly.

    Pass criteria:
    - The version key reflects the correct version after adding connections.
    """
    domain_id = "domain123"
    subject_id = "subject456"

    # Initially, version should be 0
    version = graph_manager.get_version(domain_id, subject_id, graph_type=GraphType.OUTGOING)
    assert version is None

    # Add connection and check version
    graph_manager.add_connection(domain_id, subject_id)
    version = graph_manager.get_version(domain_id, subject_id, graph_type=GraphType.OUTGOING)
    assert 1 == version

    # Add another connection and check version
    subject2_id = "subject789"
    graph_manager.add_connection(domain_id, subject2_id)
    version = graph_manager.get_version(domain_id, subject2_id, graph_type=GraphType.OUTGOING)
    assert 2 == version

    # Clean up
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    rkey1, vrkey1 = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
    rkey2, vrkey2 = graph_manager._get_graph_key(subject2_id, graph_type=GraphType.INCOMING)
    redis_client.delete(gkey, vgkey, rkey1, vrkey1, rkey2, vrkey2)


def test_incr_version(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that the version of a connection is incremented correctly.

    Pass criteria:
    - The connection score is incremented in Redis.
    - The version key reflects the new version.
    """
    domain_id = "domain123"
    subject_id = "subject456"

    graph_manager.add_connection(domain_id, subject_id)

    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert 1 == int(redis_client.zscore(gkey, subject_id))

    # Increment existing subject
    new_score = graph_manager.incr_version(domain_id, subject_id, graph_type=GraphType.OUTGOING)
    assert 2 == new_score
    assert 2 == int(redis_client.zscore(gkey, subject_id))
    assert 2 == int(redis_client.get(vgkey))

    # Increment a subject never seen before
    subject2_id = "subject789"
    new_score = graph_manager.incr_version(domain_id, subject2_id, graph_type=GraphType.OUTGOING)
    assert 3 == new_score

    # Clean up
    rkey1, vrkey1 = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
    rkey2, vrkey2 = graph_manager._get_graph_key(subject2_id, graph_type=GraphType.INCOMING)
    redis_client.delete(gkey, vgkey, rkey1, vrkey1, rkey2, vrkey2)


def test_remove_connection(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that a connection is removed correctly.

    Pass criteria:
    - The outgoing connection score is set to -2 after removal.
    - The incoming connection score is also set to -2 after removal.
    - The version keys for both graphs are incremented.
    """
    domain_id = "domain123"
    subject_id = "subject456"

    # Add connection first
    graph_manager.add_connection(domain_id, subject_id)

    # Remove connection
    graph_manager.remove_connection(domain_id, subject_id)

    # Check outgoing connection removal
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert -2 == int(redis_client.zscore(gkey, subject_id))
    assert 2 == int(redis_client.get(vgkey))

    # Check incoming connection removal
    rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
    assert -2 == int(redis_client.zscore(rkey, domain_id))
    assert 2 == int(redis_client.get(vrkey))

    # Clean up
    redis_client.delete(gkey, vgkey, rkey, vrkey)


def test_remove_connection_hard_delete(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that a connection is hard-deleted correctly.

    Pass criteria:
    - The outgoing and incoming connection entries are removed entirely.
    - The existing version keys are not incremented during hard delete.
    """
    domain_id = "domain123"
    subject_id = "subject456"

    # Add connection first
    graph_manager.add_connection(domain_id, subject_id)

    # Hard-delete connection
    graph_manager.remove_connection(domain_id, subject_id, soft=False)

    # Check outgoing connection removal
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert redis_client.zscore(gkey, subject_id) is None
    assert 1 == int(redis_client.get(vgkey))

    # Check incoming connection removal
    rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
    assert redis_client.zscore(rkey, domain_id) is None
    assert 1 == int(redis_client.get(vrkey))

    # Clean up
    redis_client.delete(gkey, vgkey, rkey, vrkey)


def test_remove_domain(graph_manager: GraphManager, redis_client: Redis) -> None:
    """
    Test that a domain and its incoming connections are removed correctly.

    Pass criteria:
    - The outgoing connections and version key for the domain are deleted.
    - All incoming connections from subjects to the domain are removed.
    """
    domain_id = "domain123"
    subject_ids = ["subject456", "subject789"]

    # Add connections first
    graph_manager.add_connection_list(domain_id, subject_ids)

    # Remove domain
    graph_manager.remove_domain(domain_id)

    # Check outgoing connections removal
    gkey, vgkey = graph_manager._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
    assert redis_client.zcard(gkey) == 0
    assert redis_client.get(vgkey) is None

    # Check incoming connections removal
    for subject_id in subject_ids:
        rkey, _ = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        assert redis_client.zscore(rkey, domain_id) is None

    # Clean up
    redis_client.delete(gkey, vgkey)
    for subject_id in subject_ids:
        rkey, vrkey = graph_manager._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        redis_client.delete(rkey, vrkey)
