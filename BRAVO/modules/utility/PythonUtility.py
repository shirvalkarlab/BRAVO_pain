# -*- coding: utf-8 -*-
"""
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
@date: Fri Oct 16 11:06:37 2020
"""

import numpy as np

def listSort(oldList, newIndexes):
    return [oldList[i] for i in newIndexes]

def _deduplication_key(value):
    if isinstance(value, list):
        return (list, tuple(_deduplication_key(item) for item in value))
    if isinstance(value, tuple):
        return (tuple, tuple(_deduplication_key(item) for item in value))
    if isinstance(value, dict):
        return (dict, frozenset((key, _deduplication_key(item)) for key, item in value.items()))
    # NaN is not equal to itself; do not let set identity shortcuts merge it.
    if value != value:
        raise ValueError("Non-reflexive equality")
    hash(value)
    return value


def uniqueListOfDicts(listOfDicts, keys):
    """Keep the first equal record without repeatedly scanning prior records."""
    unique = []
    seen = set()
    for item in listOfDicts:
        if any(key not in item for key in keys):
            unique.append(item)
            continue
        try:
            key = tuple(_deduplication_key(item[field]) for field in keys)
        except (TypeError, ValueError):
            # Retain historical comparison for uncommon unhashable values.
            if len(_uniqueListOfDictsByComparison(unique + [item], keys)) > len(unique):
                unique.append(item)
            continue
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _uniqueListOfDictsByComparison(listOfDicts, keys):
    uniqueDicts = []
    for dictItem in listOfDicts:
        found = False
        for currentItem in uniqueDicts:
            match = True
            for key in keys:
                if key not in dictItem or key not in currentItem:
                    match = False
                    break

                val1 = dictItem[key]
                val2 = currentItem[key]

                if isinstance(val1, list) and isinstance(val2, list):
                    if len(val1) != len(val2):
                        match = False
                        break
                    for n, (a, b) in enumerate(zip(val1, val2)):
                        if a != b:
                            match = False
                            break
                    if not match:
                        break
                else:
                    if val1 != val2:
                        match = False
                        break

            if match:
                found = True
                break

        if not found:
            uniqueDicts.append(dictItem)

    return uniqueDicts

def unwrap(x, cap=None):
    if cap is None:
        cap = np.max(x) + 1
    
    unwrappedX = np.array(range(len(x)))
    unwrappedX[0] = x[0]
    currentRolls = 0
    for n in range(1,len(x)):
        if x[n] < x[n-1]:
            currentRolls += cap
        unwrappedX[n] = x[n] + currentRolls
    
    return unwrappedX

def rangeSelection(array, minMax, type="exclusive"):
    if type=="exclusive":
        return np.bitwise_and(array < minMax[1], array > minMax[0])
    else:
        return np.bitwise_and(array <= minMax[1], array >= minMax[0])

def findClosest(array, value):
    index = np.argmin(np.abs(np.array(array)-value))
    return array[index], index

def listSelection(oldList, boolArray):
    newList = list()
    for i in range(len(boolArray)):
        if boolArray[i]:
            newList.append(oldList[i])
    return newList

def ifAllConditions(*conditions):
    baseCondition = np.ones(conditions[0].shape,dtype=bool)
    for i in range(len(conditions)):
        baseCondition = np.bitwise_and(baseCondition, conditions[i].flatten())
    return baseCondition

def ifOrConditions(*conditions):
    baseCondition = np.zeros(conditions[0].shape,dtype=bool)
    for i in range(len(conditions)):
        baseCondition = np.bitwise_or(baseCondition, conditions[i].flatten())
    return baseCondition

def iterativeCompare(listItems, comparedItem, compare="less"):
    result = np.ndarray((len(listItems),1),dtype="bool")
    n = 0
    for item in listItems:
        if compare == "less":
            result[n] = item < comparedItem
        elif compare == "equal":
            result[n] = item == comparedItem
        elif compare == "more":
            result[n] = item > comparedItem
        else:
            raise TypeError("{0} is not a valid compare argument".format(compare))
        n += 1
    return result

def uniqueList(listItems):
    uniqueList = list()
    for item in listItems:
        unique = True
        for existingItem in uniqueList:
            if existingItem == item:
               unique = False 
        
        if unique:
            uniqueList.append(item)
            
    return uniqueList
