# Scoring a Run Against an Observed Extent

Any finished run can be scored against an observed deposit or affected area supplied by the user (GeoJSON or zipped shapefile polygons, or a 0/1 GeoTIFF), for the same event. The model extent is the cells where the flow reached at least a chosen depth (default 0.3 m). On the run's own grid, inside the analysed area:

```
hits = model and observed;  false alarms = model, not observed;  misses = observed, not model
CSI = hits / (hits + false alarms + misses)        POD = hits / (hits + misses)
FAR = false alarms / (hits + false alarms)         F1 = 2 hits / (2 hits + false alarms + misses)        bias = (hits + false alarms)/(hits + misses)
```

A perfect match gives CSI 1 and disjoint extents give 0 (tested). This is the only route to validating runout extent. No mapped Pakistani deposit is on the server, so **no real score exists yet**; one supplied event, with a rainfall record, would allow calibrating the friction parameters against it (Ch. {{ch:runout_calibration}}).
