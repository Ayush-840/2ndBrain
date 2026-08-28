---
title: "Temporal Databases"
tags: [databases, temporal, data-modeling]
created: 2026-08-18
---

# Temporal Databases

## Bitemporal Data
Bitemporal data combines two independent time dimensions:
- **Transaction time**: When the data was stored in the database
- **Valid time**: When the data was true in the real world

This allows reconstruction of the database state at any past point in time, and tracking when corrections or updates were made.

## SQL:2011 Temporal Features
The SQL:2011 standard introduced:
- `PERIOD AS` syntax for defining valid-time periods
- `SYSTEM_TIME` for automatic transaction-time tracking
- Temporal join operations
- `FOR SYSTEM_TIME AS OF` queries

## Neo4j Temporal Graphs
Neo4j supports temporal queries through APOC procedures and date/time types. For graph databases, bi-temporal modeling means adding `valid_from`, `valid_to`, and `recorded_at` properties to relationship types, enabling point-in-time graph traversals.

## Graphiti Approach
Graphiti (by Zep AI) implements bi-temporal knowledge graphs for AI memory. Key innovations:
- Facts carry validity windows
- New information supersedes old without deleting history
- Community detection for topic clustering
- Hybrid search combining vector similarity with graph traversal
