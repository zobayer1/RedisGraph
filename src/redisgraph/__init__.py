"""redisgraph

This package provides classes and utilities for managing domain-to-member connection graphs using Redis as the backend.
It supports adding, removing, and querying connections, as well as versioning and efficient graph operations for domain
relationships.
"""

from enum import Enum
from typing import List, Optional, Tuple

from redis import Redis


class GraphType(str, Enum):
    """
    Enumeration of graph types for domain connections.

    OUTGOING: Represents outgoing connections from a domain.
    INCOMING: Represents incoming connections to a domain.
    """

    OUTGOING = "outgoing"
    INCOMING = "incoming"


class GraphManager:
    """
    Manages domain-to-member connection graphs using Redis as the backend.

    Provides methods to add, remove, and query connections between domains and subjects,
    supporting versioning and efficient graph operations.
    """

    def __init__(self, client: Redis, prefix: str = "graph", namespace: str = "test") -> None:
        """
        Initialize a new GraphManager instance.

        Args:
            client (Redis): Redis client instance used for all operations.
            prefix (str, optional): Prefix for all Redis keys. Defaults to "graph".
            namespace (str, optional): Tag to identify the graph's domain context. Defaults to "test".
        """
        # Default values are for testing purposes; override in production
        self.client = client
        self.prefix = prefix
        self.namespace = namespace

    def _get_graph_key(self, domain_id: str, graph_type: GraphType = GraphType.OUTGOING) -> Tuple[str, str]:
        """
        Generate the Redis graph key and version key for a given domain and graph type.

        Args:
            domain_id (str): The domain identifier.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.

        Returns:
            Tuple[str, str]: A tuple containing the graph key and the corresponding version key.
        """
        # Do not update key pattern as it will affect existing data
        key = f"{self.prefix}:connection:{self.namespace}:{graph_type.value}:{domain_id}"
        return key, f"{key}:version"

    def add_connection(self, domain_id: str, subject_id: str) -> None:
        """
        Add an outgoing connection from `domain_id` to `subject_id` and the corresponding incoming connection.

        This method updates the outgoing connections ZSET for `domain_id` and the incoming connections ZSET for
        `subject_id`. Each connection is versioned using an incrementing counter.

        Args:
            domain_id (str): The identifier of the source domain.
            subject_id (str): The identifier of the target subject to connect.
        """
        # Add outgoing connection (domain owns subject)
        gkey, vkey = self._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
        self.client.zadd(gkey, {subject_id: self.client.incr(vkey)})
        # Add corresponding incoming connection (subject owned by domain)
        rkey, vkey = self._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        self.client.zadd(rkey, {domain_id: self.client.incr(vkey)})

    def add_connection_list(self, domain_id: str, subject_ids: List[str]) -> None:
        """
        Add multiple outgoing connections from `domain_id` to each `subject_id` in the list.

        This is a shorthand method that calls `add_connection` for each subject ID provided.

        Args:
            domain_id (str): The identifier of the source domain.
            subject_ids (List[str]): A list of target subject identifiers to connect.
        """
        # Loop through each subject ID and add the connections (non-atomic)
        for subject_id in subject_ids:
            self.add_connection(domain_id, subject_id)

    def get_all_connections(self, domain_id: str, graph_type: GraphType = GraphType.OUTGOING) -> List[str]:
        """
        Retrieve all active connections for a given domain.

        This method fetches all members from the specified graph type (OUTGOING or INCOMING) for the given domain.

        Args:
            domain_id (str): The identifier of the domain whose connections are queried.
            graph_type (GraphType): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.

        Returns:
            List[str]: A list of member IDs connected to the specified domain.
        """
        # Only fetch active connections (positive scores)
        gkey, _ = self._get_graph_key(domain_id, graph_type)
        return list(self.client.zrangebyscore(gkey, min="(0", max="+inf"))

    def get_connections(
        self, domain_id: str, graph_type: GraphType = GraphType.OUTGOING, cut_off: int = 0, size: int = 100
    ) -> Tuple[List[str], List[str], int]:
        """
        Retrieve a paginated list of active connections and all removed connections for a given domain.

        Active connections are paginated using the `cut_off` parameter, which acts as a lower bound for the version
        score. The `size` parameter controls the maximum number of active connections returned in one call. Removed
        connections are fetched separately for the same score range and are not paginated.

        Args:
            domain_id (str): The identifier of the domain whose connections are queried.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.
            cut_off (int, optional): The minimum version score (exclusive) for pagination. Defaults to 0.
            size (int, optional): The maximum number of active connections to return. Defaults to 100.

        Returns:
            Tuple[List[str], List[str], int]: A tuple containing:
                - List of active connection IDs (paginated).
                - List of removed connection IDs (not paginated).
                - The version score for fetching the next page of active connections.
        """
        # Find the maximum score for the domain graph
        gkey, vkey = self._get_graph_key(domain_id, graph_type)
        current_max_str = self.client.get(vkey)
        # If no connections exist, return empty lists and zero max score
        if not current_max_str:
            return [], [], 0
        # Find active connections page
        plus_range = self.client.zrangebyscore(gkey, min=f"({cut_off}", max="+inf", start=0, num=size, withscores=True)
        # Find max score in the page
        current_max = int(current_max_str)
        max_score = current_max if not plus_range else cut_off
        active = [item[0] for item in plus_range]
        max_score = max(max_score, int(max(plus_range, key=lambda x: x[1])[1]) if plus_range else 0)
        # Find removed connections for the page
        removed = list(self.client.zrangebyscore(gkey, min=f"{-max_score}", max=f"({-cut_off}"))
        return active, removed, max_score

    def get_latest_connections(
        self, domain_id: str, graph_type: GraphType = GraphType.OUTGOING, size: int = 100
    ) -> List[str]:
        """
        Retrieve the latest active connections for a given domain.

        This method fetches the most recent members from the specified graph type (OUTGOING or INCOMING) for the
        given domain, limited by the `size` parameter.

        Args:
            domain_id (str): The identifier of the domain whose connections are queried.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.
            size (int, optional): The maximum number of active connections to return. Defaults to 100.

        Returns:
            List[str]: A list of the latest member IDs connected to the specified domain.
        """
        # Fetch the connections in descending order of scores (highest first)
        gkey, _ = self._get_graph_key(domain_id, graph_type)
        return list(self.client.zrevrangebyscore(gkey, max="+inf", min="(0", start=0, num=size))

    def get_intersection(
        self, domain_left: str, domain_right: str, graph_type: GraphType = GraphType.OUTGOING
    ) -> List[str]:
        """
        Find the common members (intersection) between two domain graphs.

        This method retrieves the set of members from both `domain_left` and `domain_right` for the specified graph
        type, and returns the list of members present in both graphs.

        Args:
            domain_left (str): The identifier of the first domain.
            domain_right (str): The identifier of the second domain.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.

        Returns:
            List[str]: A list of member IDs present in both domain graphs.
        """
        # Only intersect active members (positive scores) from left and right domains
        gkey_left, _ = self._get_graph_key(domain_left, graph_type)
        members_left = set(self.client.zrangebyscore(gkey_left, min="(0", max="+inf"))
        gkey_right, _ = self._get_graph_key(domain_right, graph_type)
        members_right = set(self.client.zrangebyscore(gkey_right, min="(0", max="+inf"))
        return list(members_left & members_right)

    def get_version(self, domain_id: str, subject_id: str, graph_type: GraphType = GraphType.OUTGOING) -> Optional[int]:
        """
        Retrieve the version (score) of a subject in a specified domain graph.

        Args:
            domain_id (str): The identifier of the domain.
            subject_id (str): The identifier of the subject whose version is queried.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.

        Returns:
            Optional[int]: The version (score) of the subject if it exists, otherwise None.
        """
        # Get the score of the subject in the specified graph using zscore
        gkey, _ = self._get_graph_key(domain_id, graph_type)
        score = self.client.zscore(gkey, subject_id)
        return int(score) if score else None

    def incr_version(self, domain_id: str, subject_id: str, graph_type: GraphType = GraphType.OUTGOING) -> int:
        """
        Increment the version (score) of a subject in a specified domain graph.

        Args:
            domain_id (str): The identifier of the domain.
            subject_id (str): The identifier of the subject whose version is to be incremented.
            graph_type (GraphType, optional): The type of graph (OUTGOING or INCOMING). Defaults to OUTGOING.
        Returns:
            int: The new version (score) of the subject
        """
        # Increase the version if subject exists or insert new with next version
        gkey, vkey = self._get_graph_key(domain_id, graph_type)
        self.client.zadd(gkey, {subject_id: self.client.incr(vkey)})
        return int(self.client.zscore(gkey, subject_id))

    def remove_connection(self, domain_id: str, subject_id: str) -> None:
        """
        Remove a connection between `domain_id` and `subject_id`.

        The outgoing connection from `domain_id` to `subject_id` is soft-deleted by assigning a negative version score,
        allowing for historical tracking. The corresponding incoming connection from `subject_id` to `domain_id` is
        permanently removed from the graph.

        Args:
            domain_id (str): The identifier of the source domain.
            subject_id (str): The identifier of the target subject to disconnect.
        """
        # Soft delete the outgoing connection by assigning a negative version
        gkey, vkey = self._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
        self.client.zadd(gkey, {subject_id: int(-1 * self.client.incr(vkey))})
        # Remove the corresponding incoming connection
        rkey, _ = self._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
        self.client.zrem(rkey, domain_id)

    def remove_domain(self, domain_id: str) -> None:
        """
        Remove all connections for a given domain.

        This method deletes all outgoing connections for the specified `domain_id` and removes the corresponding
        `domain_id` entry from the incoming connection graphs of all connected subjects. Does not check for negative
        scores, effectively cleaning up all connections.

        Args:
            domain_id (str): The identifier of the domain whose connections are to be removed.
        """
        # Fetch all subjects connected to the domain before removing the outgoing graph
        gkey, vkey = self._get_graph_key(domain_id, graph_type=GraphType.OUTGOING)
        subject_ids = self.client.zrange(gkey, 0, -1)
        self.client.delete(gkey, vkey)
        # Remove the domain from each subject's incoming graph using the fetched list
        for subject_id in subject_ids:
            rkey, _ = self._get_graph_key(subject_id, graph_type=GraphType.INCOMING)
            self.client.zrem(rkey, domain_id)


__all__ = ["GraphManager", "GraphType"]
