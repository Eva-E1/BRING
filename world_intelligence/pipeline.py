"""Full automation pipeline: enrich the whole world, with async background tasks."""
import asyncio
from rich.console import Console
from world_explorer.store import GraphStore
from world_explorer.builder_integration import BuilderInterface
from .rule_checker import RuleChecker
from .recommender import Recommender
from .duplicate_detector import DuplicateDetector

console = Console()


class EnrichmentPipeline:
    def __init__(self, store: GraphStore, builder: BuilderInterface):
        self.store = store
        self.builder = builder

    async def run_async(
        self,
        complete_layers: bool = True,
        relationships: bool = True,
        check_rules: bool = True,
        fix_rules: bool = False,
        merge_duplicates: bool = True,
        similarity_threshold: float = 0.9,
    ) -> None:
        """Execute a full enrichment pass asynchronously."""
        console.rule("[bold]Starting World Enrichment Pipeline[/]")

        tasks = []

        # 1. Complete L2/L3
        if complete_layers:
            tasks.append(asyncio.create_task(self._phase_complete_layers()))

        # 2. Relationships
        if relationships:
            tasks.append(asyncio.create_task(self._phase_relationships()))

        # 3. Rule checking
        if check_rules:
            tasks.append(asyncio.create_task(self._phase_check_rules(fix_rules)))

        # Wait for all tasks
        completed_tasks = await asyncio.gather(*tasks, return_exceptions=True)

        # Refresh store
        self.store.boot()

        # 4. Recommendations (quick)
        console.print("[cyan]Phase: Generating recommendations...[/]")
        rec = Recommender(self.store)
        missing_rel = rec.suggest_missing_relationships(top_k=10)
        if missing_rel:
            console.print("[bold]Top missing relationship suggestions:[/]")
            for r in missing_rel:
                console.print(
                    f"  {r['source_name']} ↔ {r['target_name']} (common neighbors: {r['common_neighbors']})"
                )
        new_ent = rec.suggest_new_entities()
        if new_ent:
            console.print("[bold]Suggested new entities:[/]")
            for e in new_ent:
                console.print(f"  {e['suggested_type']} based on {e['based_on_members']}")

        # 5. Automatic duplicate merging (BRING-inspired)
        if merge_duplicates:
            await self._phase_merge_duplicates(similarity_threshold)

        console.rule("[bold green]Enrichment complete[/]")

    async def _phase_complete_layers(self):
        console.print("[cyan]Completing L2/L3...[/]")
        # Use asyncio.to_thread to avoid blocking the event loop
        await asyncio.to_thread(self.builder.builder.build_L2)
        await asyncio.to_thread(self.builder.builder.build_L3)
        console.print("[green]L2/L3 completed.[/]")

    async def _phase_relationships(self):
        console.print("[cyan]Generating relationships...[/]")
        await asyncio.to_thread(self.builder.complete_relationships)
        console.print("[green]Relationships updated.[/]")

    async def _phase_check_rules(self, fix_rules: bool):
        console.print("[cyan]Checking world rules...[/]")
        checker = RuleChecker(self.store, self.builder, max_concurrent_llm=4)
        conflicts = await checker.check_all_async(auto_fix=fix_rules)
        if conflicts:
            console.print(f"[yellow]Found {len(conflicts)} rule conflicts[/]")
            if fix_rules:
                console.print("[green]Auto‑fix applied.[/]")
        else:
            console.print("[green]No rule conflicts found.[/]")

    async def _phase_merge_duplicates(self, similarity_threshold: float):
        """Automatically merge duplicate NPCs that have high embedding similarity."""
        console.print("[cyan]Checking for duplicate entities...[/]")
        try:
            detector = DuplicateDetector(
                self.store,
                similarity_threshold=similarity_threshold
            )
            duplicates = detector.find_duplicates()
            if duplicates:
                console.print(f"[yellow]Found {len(duplicates)} potential duplicate groups[/]")
                # Merge duplicates (dry_run=False to actually merge)
                merged_count = detector.merge_duplicates(dry_run=False)
                console.print(f"[green]Merged {merged_count} duplicate entities.[/]")
            else:
                console.print("[green]No duplicate entities found.[/]")
        except Exception as e:
            console.print(f"[yellow]Duplicate detection skipped: {e}[/]")

    def run(self, **kwargs):
        """Synchronous entry point for CLI; runs async pipeline."""
        asyncio.run(self.run_async(**kwargs))
