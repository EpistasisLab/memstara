import type {Snapshot} from '../types.ts';
import type {ExecutionTile} from './executionTiles.ts';
import {tileSkillConfiguration, tileSkillStages} from './tileSkills.ts';
import {skillLabel} from './displayText.ts';

export type TileSort = 'schedule' | 'auroc_desc' | 'auroc_asc';
export type TileFilters = {skill: string; sort: TileSort};
export const DEFAULT_TILE_FILTERS: TileFilters = {skill: '', sort: 'schedule'};
export const UNRECORDED_SKILL = '__unrecorded__';
export type TileFilterMetadata = {skills: string[]; auroc: number | null};

/** Read frozen execution choices and result evidence, never the current library. */
export function outputTileFilterIndex(snapshot: Snapshot, tiles: ExecutionTile[]) {
  const titles = new Map<string, string>();
  for (const config of [...Object.values(snapshot.skill_configurations ?? {}), snapshot.run_configuration]) {
    for (const skill of config?.combination_plan?.skills?.hypothesis ?? []) {
      if (!titles.has(skill.id)) titles.set(skill.id, skillLabel(skill.id, skill.title));
    }
    for (const id of config?.books?.hypothesis ?? []) if (!titles.has(id)) titles.set(id, skillLabel(id));
  }
  const metadata = new Map<number, TileFilterMetadata>();
  let unknown = false;
  for (const tile of tiles) {
    const ids = new Set<string>();
    const sources = tile.results.length ? tile.results.map(result => ({tag: result.run_tag ?? snapshot.run_tag, result}))
      : [...new Set([...tile.explanations.map(output => output.run_tag ?? snapshot.run_tag),
        ...(tile.usage?.run_tags ?? []), tile.record_run_tag])].map(tag => ({tag, result: undefined}));
    for (const {tag, result} of sources) {
      const recorded = result?.evaluation?.skills?.hypothesis;
      const chosen = tileSkillStages(tileSkillConfiguration(snapshot, tag), tile.loop, result ? [result] : [])[0].selected;
      for (const id of recorded?.length ? recorded : chosen ? [chosen.id] : []) {
        ids.add(id);
        if (!titles.has(id)) titles.set(id, skillLabel(id, chosen?.id === id ? chosen.title : undefined));
      }
    }
    if (!ids.size) unknown = true;
    const scores = tile.results.map(result => result.auc).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    metadata.set(tile.loop, {skills: [...ids], auroc: scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null});
  }
  const options = [...titles].map(([id, title]) => ({id, title})).sort((a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
  if (unknown) options.push({id: UNRECORDED_SKILL, title: 'Skill not recorded'});
  return {metadata, options};
}

/** Filter and rank the full list before pagination. Original records stay untouched. */
export function filterOutputTiles(tiles: ExecutionTile[], metadata: Map<number, TileFilterMetadata>, filters: TileFilters) {
  const selected = tiles.filter(tile => {
    if (!filters.skill) return true;
    const skills = metadata.get(tile.loop)?.skills ?? [];
    return filters.skill === UNRECORDED_SKILL ? !skills.length : skills.includes(filters.skill);
  });
  if (filters.sort === 'schedule') return selected;
  const direction = filters.sort === 'auroc_desc' ? -1 : 1;
  return selected.map((tile, index) => ({tile, index})).sort((a, b) => {
    const left = metadata.get(a.tile.loop)?.auroc ?? null, right = metadata.get(b.tile.loop)?.auroc ?? null;
    if (left === null || right === null) return left === right ? a.index - b.index : left === null ? 1 : -1;
    return (left - right) * direction || a.index - b.index;
  }).map(item => item.tile);
}
