from __future__ import annotations

from typing import Any

from shapely.geometry import shape

import ckan.plugins as p
from ckan.common import json

import ckanext.iso19115.converter as c
import ckanext.iso19115.converter.helpers as h
import ckanext.iso19115.types as t
from ckanext.iso19115.interfaces import IIso19115


class Iso19115(p.SingletonPlugin):
    p.implements(IIso19115)

    def iso19115_metadata_converter(self, data_dict: dict[str, Any]) -> c.Converter:
        return DgaConverter(data_dict)


class DgaConverter(c.Converter):
    def _add_scope(self):
        """Set scope during identification."""

    def _add_identification(self):
        super()._add_identification()
        ident = self.data.identificationInfo[0]

        topic = self.pkg.get("geospatial_topic", [])
        if isinstance(topic, str):
            topic = topic.split(",")

        container = ident.topicCategory
        if container is not None:
            for item in topic:
                code = t.mri.MD_TopicCategoryCode(item)
                container.append(code)  # type: ignore

        scope = "nonGeographicDataset"
        if spatial := self.pkg.get("spatial"):
            try:
                geometry = shape(json.loads(spatial))
            except ValueError:
                pass
            else:
                square = 4
                if len(geometry.bounds) == square:
                    w, s, e, n = geometry.bounds

                    bbox_el = t.gex.EX_GeographicBoundingBox(
                        westBoundLongitude=t.gco.Decimal(w),
                        eastBoundLongitude=t.gco.Decimal(e),
                        southBoundLatitude=t.gco.Decimal(s),
                        northBoundLatitude=t.gco.Decimal(n),
                    )

                    ident.extent = [
                        t.gex.EX_Extent(
                            description=h.cs(self.pkg.get("spatial_coverage") or ""),
                            geographicElement=[bbox_el],
                        ),
                    ]
                    scope = "nonGeographicDataset"
        self.data.metadataScope.append(
            t.mdb.MD_MetadataScope(t.mcc.MD_ScopeCode(scope), h.cs(scope))
        )

        for res in self.pkg["resources"]:
            self.data.add_identificationInfo(
                t.mri.MD_DataIdentification(
                    h.citation(res["name"], presentationForm="documentDigital"),
                    h.cs(res["description"]),
                    resourceFormat=[
                        t.mrd.MD_Format(
                            t.cit.CI_Citation(res["format"]),
                            res.get("version"),
                        )
                    ],
                )
            )
