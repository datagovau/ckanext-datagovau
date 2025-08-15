import pytest

from ckanext.datagovau.utils import dataset_duplicate_handler as ddh


@pytest.fixture
def datasets(dataset_factory):
    """Create 10 datasets.

    - 1 dataset with 1 copy (harvest score)
    - 2 pairs of datasets with 2 copies each (harvest score)
    - 5 unique datasets (no harvest or syndicate, score 1)
    - 1 dataset with syndicate flag (score 0)
    """
    # Use a dictionary to store datasets with the original dataset ID as the key
    datasets = {}

    # Dataset with 1 copy
    original_1 = dataset_factory(
        title="Dataset 1",
        notes="Notes 1",
    )
    datasets[original_1["id"]] = {
        "original": original_1,
        "copies": [
            dataset_factory(
                title="Dataset 1",
                notes="Notes 1",
                name=f"copy-harvest-{original_1['id']}",
                original_name=original_1["name"],
                extras=[{"key": "harvest", "value": True}],
            )
        ],
    }

    # Two pairs of datasets with 2 copies each
    original_2 = dataset_factory(
        title="Dataset 2",
        notes="Notes 2",
    )
    datasets[original_2["id"]] = {
        "original": original_2,
        "copies": [
            dataset_factory(
                title="Dataset 2",
                notes="Notes 2",
                name=f"copy-harvest-{original_2['id']}-1",
                original_name=original_2["name"],
                extras=[{"key": "harvest", "value": True}],
            ),
            dataset_factory(
                title="Dataset 2",
                notes="Notes 2",
                name=f"copy-harvest-{original_2['id']}-2",
                original_name=original_2["name"],
                extras=[{"key": "harvest", "value": True}],
            ),
        ],
    }

    original_3 = dataset_factory(
        title="Dataset 3",
        notes="Notes 3",
        extras=[{"key": "syndicate", "value": True}],
    )
    datasets[original_3["id"]] = {
        "original": original_3,
        "copies": [
            dataset_factory(
                title="Dataset 3",
                notes="Notes 3",
                original_name=original_3["name"],
                name=f"copy-syndicate-{original_3['id']}-1",
            ),
            dataset_factory(
                title="Dataset 3",
                notes="Notes 3",
                original_name=original_3["name"],
                name=f"copy-syndicate-{original_3['id']}-2",
            ),
        ],
    }

    # Add 5 unique datasets
    for i in range(4, 9):
        unique_dataset = dataset_factory(
            title=f"Dataset {i}",
            notes=f"Notes {i}",
        )
        datasets[unique_dataset["id"]] = {"original": unique_dataset, "copies": []}

    return datasets


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDatasetDuplicateDetector:
    @pytest.mark.usefixtures("with_plugins", "clean_db")
    def test_find_copies(self, datasets):
        for data in datasets.values():
            original_dataset = data["original"]
            copies = data["copies"]

            result = ddh.find_copies(original_dataset)

            # Assert that the original dataset is correctly identified
            assert result["is_original"]

            # Assert the correct number of duplicates are found
            assert len(result["duplicates"]) == len(copies)

            # Assert that the duplicates have the expected properties
            for duplicate, expected_duplicate in zip(result["duplicates"], copies):
                assert duplicate["original_name"] == expected_duplicate["original_name"]
                assert duplicate["title"] == expected_duplicate["title"]
                assert duplicate["notes"] == expected_duplicate["notes"]

    def test_get_metaphone_cluster_with_random_datasets(self, dataset_factory):
        """Test detector when no clusters are found due to random titles."""
        # Create a batch of random datasets
        datasets = dataset_factory.create_batch(10)

        titles = [dataset["title"] for dataset in datasets]

        cluster_results = ddh.get_metaphone_cluster(titles[0])

        # Since the titles are random, we expect no clusters to be found
        assert len(cluster_results) == 0

    @pytest.mark.parametrize(
        ("titles", "expected_clustering"),
        [
            (
                [
                    "Dataset about climate change",
                    "Climate change dataset",
                    "Climate data",
                ],
                [
                    {
                        "title": "Dataset about climate change",
                        "should_have_clusters": False,
                        "cluster_with": [],
                    },
                    {
                        "title": "Climate change dataset",
                        "should_have_clusters": True,
                        "cluster_with": ["Climate data"],
                    },
                    {
                        "title": "Climate data",
                        "should_have_clusters": True,
                        "cluster_with": ["Climate change dataset"],
                    },
                ],
            ),
            (
                ["Random Dataset A", "Completely Different Dataset B"],
                [
                    {
                        "title": "Random Dataset A",
                        "should_have_clusters": False,
                        "cluster_with": [],
                    },
                    {
                        "title": "Completely Different Dataset B",
                        "should_have_clusters": False,
                        "cluster_with": [],
                    },
                ],
            ),
        ],
    )
    def test_get_metaphone_cluster_with_custom_titles(
        self,
        dataset_factory,
        titles,
        expected_clustering,
    ):
        """Test `get_metaphone_cluster` with datasets using custom titles.

        This test checks how datasets with similar titles are clustered
        together based on metaphone keys.
        """
        datasets = {
            dataset_factory(title=clustering_info["title"])["id"]: clustering_info
            for clustering_info in expected_clustering
        }

        for dataset_id, clustering_info in datasets.items():
            title = clustering_info["title"]

            cluster_ids = ddh.get_metaphone_cluster(title)

            if clustering_info["should_have_clusters"]:
                # Get the IDs of the expected datasets to cluster with
                expected_cluster_id = [
                    id
                    for id, info in datasets.items()
                    if info["title"] in clustering_info["cluster_with"]
                ]

                # Includes the dataset itself, so size is 2
                assert len(cluster_ids) == 2
                # Verify that the dataset itself is in the cluster
                assert dataset_id in cluster_ids
                assert expected_cluster_id[0] in cluster_ids

            else:
                assert not cluster_ids
