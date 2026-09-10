from __future__ import annotations

import posixpath

from uni.devcoord.workspace_models import ResourceType


_PATH_TYPES = {ResourceType.FILE, ResourceType.TREE}


def normalize_resource_key(resource_type: ResourceType, key: str) -> str:
    value = key.strip().replace("\\", "/")
    if resource_type in _PATH_TYPES:
        value = posixpath.normpath(value).replace("\\", "/")
        if value == ".":
            value = ""
        value = value.strip("/")
    return value.casefold()


def _tree_contains(tree_key: str, other_key: str) -> bool:
    return other_key == tree_key or other_key.startswith(tree_key + "/")


def resources_overlap(
    left_type: ResourceType,
    left_key: str,
    right_type: ResourceType,
    right_key: str,
) -> bool:
    left = normalize_resource_key(left_type, left_key)
    right = normalize_resource_key(right_type, right_key)

    if left_type is ResourceType.FILE and right_type is ResourceType.FILE:
        return left == right
    if left_type is ResourceType.TREE and right_type in _PATH_TYPES:
        return _tree_contains(left, right)
    if right_type is ResourceType.TREE and left_type in _PATH_TYPES:
        return _tree_contains(right, left)
    if left_type is right_type and left_type not in _PATH_TYPES:
        return left == right
    return False
