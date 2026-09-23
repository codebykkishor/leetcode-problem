---
leetcode_id: 1
title: Two Sum
difficulty: Easy
url: https://leetcode.com/problems/two-sum/
pattern:
  - array
  - hash-table
language: Python3
date_solved: '2026-09-22'
needs_revision: false
---

# 1. Two Sum

* LeetCode: #1
* Difficulty: Easy
* Pattern: array, hash-table
* Language: Python3
* Solved: 2026-09-22
* URL: https://leetcode.com/problems/two-sum/

## Approach

Use a hash map to store each number's index as we scan the array. For every
element, check whether its complement (target - num) has already been seen.
If it has, we've found our pair in a single pass.

## Complexity

* Time: O(n)
* Space: O(n)

## Solution

See [`solution.py`](./solution.py).
