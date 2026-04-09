# Calibration Versioning

## Model
Every calibration profile is immutable once saved. Activation switches the active profile pointer.

## Required fields
- profile id
- workspace transform / offsets
- updated timestamp
- optional notes / quality score

## Operations
- save new profile
- list versions
- activate existing profile
- reload active profile into runtime

## Safety rule
Task execution must be blocked when no active calibration is loaded for task mode.
