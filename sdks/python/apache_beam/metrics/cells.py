#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
This file contains metric cell classes. A metric cell is used to accumulate
in-memory changes to a metric. It represents a specific metric in a single
context.

Cells depend on a 'dirty-bit' in the CellCommitState class that tracks whether
a cell's updates have been committed.
"""

import threading

from apache_beam.metrics.metricbase import Counter
from apache_beam.metrics.metricbase import Distribution


class CellCommitState(object):
  """Atomically tracks a cell's dirty/clean commit status.

  Reporting a metric update works in a two-step process: First, updates to the
  metric are received, and the metric is marked as 'dirty'. Later, updates are
  committed, and then the cell may be marked as 'clean'.

  The tracking of a cell's state is done conservatively: A metric may be
  reported DIRTY even if updates have not occurred.

  This class is thread-safe.
  """

  # Indicates that there have been changes to the cell since the last commit.
  DIRTY = 0
  # Indicates that there have NOT been changes to the cell since last commit.
  CLEAN = 1
  # Indicates that a commit of the current value is in progress.
  COMMITTING = 2

  def __init__(self):
    """Initializes ``CellCommitState``.

    A cell is initialized as dirty.
    """
    self._lock = threading.Lock()
    self._state = CellCommitState.DIRTY

  @property
  def state(self):
    with self._lock:
      return self._state

  def after_modification(self):
    """Indicate that changes have been made to the metric being tracked.

    Should be called after modification of the metric value.
    """
    with self._lock:
      self._state = CellCommitState.DIRTY

  def after_commit(self):
    """Mark changes made up to the last call to ``before_commit`` as committed.

    The next call to ``before_commit`` will return ``False`` unless there have
    been changes made.
    """
    with self._lock:
      if self._state == CellCommitState.COMMITTING:
        self._state = CellCommitState.CLEAN

  def before_commit(self):
    """Check the dirty state, and mark the metric as committing.

    After this call, the state is either CLEAN, or COMMITTING. If the state
    was already CLEAN, then we simply return. If it was either DIRTY or
    COMMITTING, then we set the cell as COMMITTING (e.g. in the middle of
    a commit).

    After a commit is successful, ``after_commit`` should be called.

    Returns:
      A boolean, which is false if the cell is CLEAN, and true otherwise.
    """
    with self._lock:
      if self._state == CellCommitState.CLEAN:
        return False
      self._state = CellCommitState.COMMITTING
      return True


class MetricCell(object):
  """Accumulates in-memory changes to a metric.

  A MetricCell represents a specific metric in a single context and bundle.
  All subclasses must be thread safe, as these are used in the pipeline runners,
  and may be subject to parallel/concurrent updates. Cells should only be used
  directly within a runner.
  """
  def __init__(self):
    self.commit = CellCommitState()
    self._lock = threading.Lock()

  def get_cumulative(self):
    raise NotImplementedError


class CounterCell(Counter, MetricCell):
  """Tracks the current value and delta of a counter metric.

  Each cell tracks the state of a metric independently per context per bundle.
  Therefore, each metric has a different cell in each bundle, cells are
  aggregated by the runner.

  This class is thread safe.
  """
  def __init__(self, *args):
    super(CounterCell, self).__init__(*args)
    self.value = 0

  def combine(self, other):
    result = CounterCell()
    result.inc(self.value + other.value)
    return result

  def inc(self, n=1):
    with self._lock:
      self.value += n
      self.commit.after_modification()

  def get_cumulative(self):
    with self._lock:
      return self.value


class DistributionCell(Distribution, MetricCell):
  """Tracks the current value and delta for a distribution metric.

  Each cell tracks the state of a metric independently per context per bundle.
  Therefore, each metric has a different cell in each bundle, that is later
  aggregated.

  This class is thread safe.
  """
  def __init__(self, *args):
    super(DistributionCell, self).__init__(*args)
    self.data = DistributionData(0, 0, None, None)

  def combine(self, other):
    result = DistributionCell()
    result.data = self.data.combine(other.data)
    return result

  def update(self, value):
    with self._lock:
      self.commit.after_modification()
      self._update(value)

  def _update(self, value):
    value = int(value)
    self.data.count += 1
    self.data.sum += value
    self.data.min = (value
                     if self.data.min is None or self.data.min > value
                     else self.data.min)
    self.data.max = (value
                     if self.data.max is None or self.data.max < value
                     else self.data.max)

  def get_cumulative(self):
    with self._lock:
      return self.data.get_cumulative()


class DistributionResult(object):
  """The result of a Distribution metric.
  """
  def __init__(self, data):
    self.data = data

  def __eq__(self, other):
    return self.data == other.data

  def __repr__(self):
    return '<DistributionResult(sum={}, count={}, min={}, max={})>'.format(
        self.sum,
        self.count,
        self.min,
        self.max)

  @property
  def max(self):
    return self.data.max

  @property
  def min(self):
    return self.data.min

  @property
  def count(self):
    return self.data.count

  @property
  def sum(self):
    return self.data.sum

  @property
  def mean(self):
    """Returns the float mean of the distribution.

    If the distribution contains no elements, it returns None.
    """
    if self.data.count == 0:
      return None
    return float(self.data.sum)/self.data.count


class DistributionData(object):
  """The data structure that holds data about a distribution metric.

  Distribution metrics are restricted to distributions of integers only.

  This object is not thread safe, so it's not supposed to be modified
  by other than the DistributionCell that contains it.
  """
  def __init__(self, sum, count, min, max):
    self.sum = sum
    self.count = count
    self.min = min
    self.max = max

  def __eq__(self, other):
    return (self.sum == other.sum and
            self.count == other.count and
            self.min == other.min and
            self.max == other.max)

  def __neq__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return '<DistributionData(sum={}, count={}, min={}, max={})>'.format(
        self.sum,
        self.count,
        self.min,
        self.max)

  def get_cumulative(self):
    return DistributionData(self.sum, self.count, self.min, self.max)

  def combine(self, other):
    if other is None:
      return self

    new_min = (None if self.min is None and other.min is None else
               min(x for x in (self.min, other.min) if x is not None))
    new_max = (None if self.max is None and other.max is None else
               max(x for x in (self.max, other.max) if x is not None))
    return DistributionData(
        self.sum + other.sum,
        self.count + other.count,
        new_min,
        new_max)

  @classmethod
  def singleton(cls, value):
    return DistributionData(value, 1, value, value)


class MetricAggregator(object):
  """Base interface for aggregating metric data during pipeline execution."""
  def zero(self):
    raise NotImplementedError

  def combine(self, updates):
    raise NotImplementedError

  def result(self, x):
    raise NotImplementedError


class CounterAggregator(MetricAggregator):
  """Aggregator for Counter metric data during pipeline execution.

  Values aggregated should be ``int`` objects.
  """
  def zero(self):
    return 0

  def combine(self, x, y):
    return int(x) + int(y)

  def result(self, x):
    return int(x)


class DistributionAggregator(MetricAggregator):
  """Aggregator for Distribution metric data during pipeline execution.

  Values aggregated should be ``DistributionData`` objects.
  """
  def zero(self):
    return DistributionData(0, 0, None, None)

  def combine(self, x, y):
    return x.combine(y)

  def result(self, x):
    return DistributionResult(x.get_cumulative())
