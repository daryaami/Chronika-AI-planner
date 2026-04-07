"""
Live embeddings semantic similarity test.
Not run by default (slow, requires local model or remote download).

PowerShell:
  $env:RUN_EMBEDDINGS_INTEGRATION="1"
  py manage.py test assistant.tests.integration.test_embeddings_semantic_similarity
"""

import os
import unittest

from django.test import SimpleTestCase

from assistant.integrations.embeddings_model import EmbeddingsModelProvider


def _dot(vec_a, vec_b):
    return sum(a * b for a, b in zip(vec_a, vec_b))


def _print_similarity_matrix(tasks, matrix):
    print("\n--- Embeddings cosine similarity matrix ---")
    header = [" " * 24] + [f"{i:>6}" for i in range(len(tasks))]
    print("".join(header))
    for i, row in enumerate(matrix):
        label = tasks[i][:22]
        left = f"[{i}] {label:<22}"
        cells = "".join(f"{score:6.2f}" for score in row)
        print(f"{left}{cells}")
    print("\nLegend:")
    for i, task in enumerate(tasks):
        print(f"  [{i}] {task}")


@unittest.skipUnless(
    os.environ.get("RUN_EMBEDDINGS_INTEGRATION") == "1",
    "Set RUN_EMBEDDINGS_INTEGRATION=1 to run live embeddings tests",
)
class EmbeddingsSemanticSimilarityTests(SimpleTestCase):
    def test_paraphrases_are_most_similar(self):
        tasks = [
            "Полить цветы",
            "Устроить полив",
            "Подготовить презентацию",
            "Защитить презентацию",
            "Сделать презентацию",
            "Заняться йогой",
            "Йога",
            "Купить продукты",
            "Сходить в магазин",
        ]

        vectors = EmbeddingsModelProvider.encode(
            tasks,
            normalize_embeddings=True,
            convert_to_numpy=True,
            batch_size=32,
        )
        vectors = [v.tolist() for v in vectors]

        matrix = []
        for i, vec_i in enumerate(vectors):
            row = []
            for j, vec_j in enumerate(vectors):
                if i == j:
                    row.append(1.0)
                else:
                    row.append(_dot(vec_i, vec_j))
            matrix.append(row)

        _print_similarity_matrix(tasks, matrix)

        expected_pairs = {
            "Полить цветы": {"Устроить полив"},
            "Йога": {"Заняться йогой"},
            "Купить продукты": {"Сходить в магазин"},
            # Для "Подготовить презентацию" в зависимости от модели ближайшим
            # может быть как "Сделать презентацию", так и "Защитить презентацию".
            "Подготовить презентацию": {"Сделать презентацию", "Защитить презентацию"},
        }

        task_to_idx = {task: idx for idx, task in enumerate(tasks)}
        for source_task, allowed_best_matches in expected_pairs.items():
            src_idx = task_to_idx[source_task]
            best_idx = max(
                (j for j in range(len(tasks)) if j != src_idx),
                key=lambda j: matrix[src_idx][j],
            )
            best_task = tasks[best_idx]
            self.assertIn(
                best_task,
                allowed_best_matches,
                msg=(
                    f"Для '{source_task}' ожидалась близкая по смыслу задача из "
                    f"{sorted(allowed_best_matches)}, но модель выбрала '{best_task}'."
                ),
            )
