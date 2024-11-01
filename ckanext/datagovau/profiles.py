from ckanext.dcat.profiles import SchemaOrgProfile
from ckanext.dcat.profiles.base import RDF, BNode, Literal, namespaces


class DgaSchemaOrgProfile(SchemaOrgProfile):
    def additional_fields(self, dataset_ref, dataset_dict):
        # Add optional creator ################################################
        creator_details = BNode()
        self.g.add((creator_details, RDF.type, namespaces["schema"].Organization))
        self.g.add((dataset_ref, namespaces["schema"].creator, creator_details))

        creator_name = dataset_dict["organization"]["title"]
        self.g.add((creator_details, namespaces["schema"].name, Literal(creator_name)))

        # set description placeholder #########################################
        desc = namespaces["schema"].description
        if not list(self.g[dataset_ref:desc]):
            self.g.add((dataset_ref, desc, Literal("---description is missing---")))
