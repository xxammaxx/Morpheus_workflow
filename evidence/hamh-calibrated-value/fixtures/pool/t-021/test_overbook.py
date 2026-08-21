"""Tests for overbook (task fixture t-021)."""

import pytest

from overbook import check_conflicts

D = "2026-08-21T"


def b(resource, start, end):
    return (resource, start, end)


def test_no_conflict_empty():
    assert check_conflicts([]) is False


def test_single_booking():
    assert check_conflicts([b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z")]) is False


def test_non_overlapping_same_resource():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z"),
        b("r1", f"{D}10:30:00Z", f"{D}11:00:00Z"),
    ]
    assert check_conflicts(bookings) is False


def test_touching_bookings_no_conflict():
    # one ends exactly when the other starts -> NO conflict (half-open)
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z"),
        b("r1", f"{D}10:00:00Z", f"{D}11:00:00Z"),
    ]
    assert check_conflicts(bookings) is False


def test_overlap_conflict():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}10:30:00Z"),
        b("r1", f"{D}10:00:00Z", f"{D}11:00:00Z"),
    ]
    assert check_conflicts(bookings) is True


def test_contained_booking_conflicts():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}12:00:00Z"),
        b("r1", f"{D}10:00:00Z", f"{D}11:00:00Z"),
    ]
    assert check_conflicts(bookings) is True


def test_identical_bookings_conflict():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z"),
        b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z"),
    ]
    assert check_conflicts(bookings) is True


def test_different_resources_never_conflict():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}12:00:00Z"),
        b("r2", f"{D}09:00:00Z", f"{D}12:00:00Z"),
    ]
    assert check_conflicts(bookings) is False


def test_unsorted_input():
    bookings = [
        b("r1", f"{D}11:00:00Z", f"{D}12:00:00Z"),
        b("r1", f"{D}08:00:00Z", f"{D}09:00:00Z"),
        b("r1", f"{D}10:30:00Z", f"{D}11:30:00Z"),  # overlaps 11:00-12:00
    ]
    assert check_conflicts(bookings) is True


def test_multi_resource_conflict_isolated():
    bookings = [
        b("r1", f"{D}09:00:00Z", f"{D}10:00:00Z"),
        b("r2", f"{D}09:00:00Z", f"{D}10:00:00Z"),
        b("r2", f"{D}09:30:00Z", f"{D}10:30:00Z"),  # conflict only on r2
    ]
    assert check_conflicts(bookings) is True
