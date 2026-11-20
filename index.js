/**
 * Ships the "UE for Clickteam Fusion 2.5" skill as a DeepSeek Harness skill
 * provider.
 *
 * `assets/ue-ctf25` is the original Codex plugin's `skills/ue-ctf25` tree,
 * unmodified: `SKILL.md`, `references/`, and `scripts/`. The candidate's
 * `resourceBase` is that directory, so the relative links inside the
 * instructions resolve without rewriting the skill body.
 */

import { readFile } from 'node:fs/promises'
import { isAbsolute, join, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Provider label reported in skill metadata, logs, and `<skill_content>`. */
const PROVIDER = 'ue-ctf25'
/**
 * Rank used by packaged skill providers. A project skill of the same name
 * (`.dsh/skills`, `.agents/skills`) still outranks this one.
 */
const RANK = 600
/** Skill directory name inside `assets/`. */
const ASSET_SKILL = 'ue-ctf25'
/** Public skill-name grammar. */
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** Cordis plugin name. */
export const name = 'skill-ue-ctf25'
/** The skill registry this row contributes to. */
export const inject = ['skills']

/**
 * Register the `ue-ctf25` skill.
 * @param ctx - context carrying `ctx.skills`.
 * @param config - optional `assetRoot` override; defaults to the packaged assets.
 */
export function apply(ctx, config = {}) {
  const assetRoot = config.assetRoot ?? fileURLToPath(new URL('./assets/', import.meta.url))
  if (!isAbsolute(assetRoot)) throw new Error('skill-ue-ctf25: assetRoot must be an absolute directory')
  const directory = join(assetRoot, ASSET_SKILL)
  const skillFile = join(directory, 'SKILL.md')
  const reported = new Map()

  /** Missing or invalid skill files stay unavailable until the file changes. */
  function failed(error, persistent) {
    const failure = String(error)
    if (reported.get(skillFile) !== failure) {
      reported.set(skillFile, failure)
      ctx.logger.warn(`skill-ue-ctf25: "${ASSET_SKILL}" is unavailable: ${failure}`)
    }
    return { kind: 'failed', error, persistent }
  }

  async function readSkill(signal) {
    let raw
    try {
      raw = await readFile(skillFile, { encoding: 'utf8', signal })
    } catch (error) {
      if (signal?.aborted === true) throw error
      const code = error instanceof Error && 'code' in error ? error.code : undefined
      return failed(error, code === 'ENOENT' || code === 'ENOTDIR')
    }
    try {
      const skill = parseSkill(raw, skillFile)
      reported.delete(skillFile)
      return { kind: 'loaded', skill }
    } catch (error) {
      return failed(error, true)
    }
  }

  /** Summary fields shared by the catalog candidate and the loaded definition. */
  function summary(skill) {
    return {
      name: skill.name,
      description: skill.description,
      ...skill.whenToUse === undefined ? {} : { whenToUse: skill.whenToUse },
      invocation: skill.invocation,
      provider: PROVIDER,
      source: 'bundled',
      resourceBase: { kind: 'directory', path: directory.split(sep).join('/') },
      path: skillFile,
    }
  }

  ctx.skills.registerProvider((control) => ({
    name: PROVIDER,
    async list(options) {
      const read = await readSkill(options.signal)
      if (read.kind === 'failed') return { candidates: [], complete: read.persistent }
      return { candidates: [{ ...summary(read.skill), rank: RANK, locator: skillFile }], complete: true }
    },
    async get(_candidate, options) {
      const read = await readSkill(options.signal)
      if (read.kind === 'failed') {
        if (!read.persistent) throw read.error
        control.invalidate()
        return undefined
      }
      return { ...summary(read.skill), content: read.skill.content }
    },
  }))
}

/**
 * Read the frontmatter fields this plugin needs.
 *
 * Supports the plain `key: value` form the shipped `SKILL.md` uses, including
 * quoted values and the DSH invocation switches; YAML block scalars, anchors,
 * and nesting are rejected with a message naming the file.
 * @param raw - complete `SKILL.md` text.
 * @param path - file path used in error messages.
 * @returns the skill name, description, optional routing hint, invocation policy, and body.
 */
export function parseSkill(raw, path) {
  const lines = raw.split(/\r?\n/)
  if (lines[0] !== '---') throw new Error(`${path}: missing YAML frontmatter`)
  const end = lines.indexOf('---', 1)
  if (end < 0) throw new Error(`${path}: unterminated YAML frontmatter`)
  const fields = new Map()
  for (const line of lines.slice(1, end)) {
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue
    const match = /^([A-Za-z][\w-]*):[ \t]*(.*)$/.exec(line)
    if (match === null) throw new Error(`${path}: unsupported frontmatter line "${line}"`)
    const value = unquote(match[2])
    if (value === '|' || value === '>' || value.startsWith('|') || value.startsWith('>')) {
      throw new Error(`${path}: block scalars are unsupported for "${match[1]}"`)
    }
    fields.set(match[1], value)
  }
  const skillName = fields.get('name')
  if (skillName === undefined || !SKILL_NAME.test(skillName)) {
    throw new Error(`${path}: frontmatter requires a kebab-case name`)
  }
  const description = fields.get('description')
  if (description === undefined || description.length === 0) {
    throw new Error(`${path}: frontmatter requires a description`)
  }
  const whenToUse = fields.get('whenToUse')
  return {
    name: skillName,
    description,
    ...whenToUse === undefined || whenToUse.length === 0 ? {} : { whenToUse },
    invocation: {
      modelInvocable: frontmatterBoolean(fields, 'disable-model-invocation', path, false) === false,
      userInvocable: frontmatterBoolean(fields, 'user-invocable', path, true),
    },
    content: lines.slice(end + 1).join('\n').trim(),
  }
}

/** Strip one matching pair of quotes from a frontmatter value. */
function unquote(value) {
  const trimmed = value.trim()
  if (trimmed.length > 1 && ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'")))) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

/** Read a frontmatter switch, falling back to `fallback` when the key is absent. */
function frontmatterBoolean(fields, key, path, fallback) {
  const value = fields.get(key)
  if (value === undefined) return fallback
  switch (value.toLowerCase()) {
    case 'true':
    case 'yes':
    case 'on':
    case '1':
      return true
    case 'false':
    case 'no':
    case 'off':
    case '0':
    case '':
      return false
    default:
      throw new Error(`${path}: frontmatter field "${key}" must be a boolean`)
  }
}
