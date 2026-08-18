/**
 * AutoDev contract validator — JS twin of runtime/contracts/validator.py
 * (dependency-free JSON Schema subset). Used inside n8n Code nodes for the
 * deterministic gates. Must agree with the Python validator on every schema —
 * cross-language equivalence is part of the test matrix.
 *
 * API: validateAutodevContract(payload, schema) -> {ok, contract, errors, error_count}
 */
function validateAutodevContract(payload, schema) {
  const errors = [];
  try {
    if (schema && schema.type === 'object' && typeof payload !== 'object') {
      errors.push('$: expected object, got ' + typeof payload);
    } else {
      validateNode(payload, schema, '$', errors, schema);
    }
  } catch (e) {
    return { ok: false, contract: schema && schema.$id, errors: ['validator error: ' + e.message], error_count: 1 };
  }
  const contract = schema && schema.$id ? schema.$id : null;
  return { ok: errors.length === 0, contract, errors, error_count: errors.length };
}

function validateNode(value, schema, path, errors, root) {
  if (schema === true) return;
  if (schema === false) { errors.push(path + ': schema forbids value'); return; }

  if (schema.$ref) {
    const name = schema.$ref.replace('#/$defs/', '');
    const defs = (root.$defs || {})[name];
    if (!defs) throw new Error('unresolved $ref ' + schema.$ref);
    validateNode(value, defs, path, errors, root);
    return;
  }

  if (schema.oneOf) {
    let matched = 0;
    for (const sub of schema.oneOf) {
      const subErrors = [];
      validateNode(value, sub, path, subErrors, root);
      if (subErrors.length === 0) matched++;
    }
    if (matched !== 1) {
      errors.push(path + ': must match exactly one of ' + schema.oneOf.length + ' alternatives (matched ' + matched + ')');
    }
    return;
  }

  if (schema.type) {
    const expected = Array.isArray(schema.type) ? schema.type : [schema.type];
    const ok = expected.some((t) => typeCheck(value, t));
    if (!ok) {
      errors.push(path + ': expected ' + expected.join(' or ') + ', got ' + jsTypeName(value));
      return;
    }
  }

  if (schema.const !== undefined) {
    if (JSON.stringify(value) !== JSON.stringify(schema.const)) {
      errors.push(path + ': must equal ' + pyRepr(schema.const));
    }
    return;
  }

  if (schema.enum) {
    if (!schema.enum.some((e) => JSON.stringify(e) === JSON.stringify(value))) {
      errors.push(path + ': must be one of [' + schema.enum.map(pyRepr).join(', ') + ']');
    }
    return;
  }

  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(path + ': length must be >= ' + schema.minLength);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(path + ': length must be <= ' + schema.maxLength);
    }
    if (schema.pattern) {
      const re = new RegExp(schema.pattern);
      if (!re.test(value)) errors.push(path + ': must match pattern ' + pyRepr(schema.pattern));
    }
    return;
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(path + ': must be >= ' + schema.minimum);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(path + ': must be <= ' + schema.maximum);
    }
    return;
  }

  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(path + ': must have at least ' + schema.minItems + ' items');
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(path + ': must have at most ' + schema.maxItems + ' items');
    }
    if (schema.items) {
      value.forEach((item, i) => validateNode(item, schema.items, path + '[' + i + ']', errors, root));
    }
    return;
  }

  if (typeof value === 'object' && value !== null) {
    const props = schema.properties || {};
    for (const [name, sub] of Object.entries(props)) {
      if (name in value) validateNode(value[name], sub, path + '.' + name, errors, root);
    }
    for (const name of schema.required || []) {
      if (!(name in value)) errors.push(path + ': ' + name + ' is required');
    }
    const addl = schema.additionalProperties === undefined ? true : schema.additionalProperties;
    if (addl === false) {
      for (const key of Object.keys(value)) {
        if (!(key in props)) errors.push(path + ': additional property ' + pyRepr(key) + ' not allowed');
      }
    } else if (typeof addl === 'object') {
      for (const key of Object.keys(value)) {
        if (!(key in props)) validateNode(value[key], addl, path + '.' + key, errors, root);
      }
    }
    return;
  }
}

function typeCheck(value, expected) {
  switch (expected) {
    case 'integer': return typeof value === 'number' && Number.isInteger(value);
    case 'number': return typeof value === 'number' && Number.isFinite(value);
    case 'string': return typeof value === 'string';
    case 'boolean': return typeof value === 'boolean';
    case 'object': return typeof value === 'object' && value !== null && !Array.isArray(value);
    case 'array': return Array.isArray(value);
    case 'null': return value === null;
    default: throw new Error('unsupported type ' + expected);
  }
}

function jsTypeName(value) {
  if (value === null) return 'NoneType';
  if (Array.isArray(value)) return 'list';
  if (typeof value === 'object') return 'dict';
  if (typeof value === 'string') return 'str';
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'float';
  return typeof value;
}

function pyRepr(value) {
  if (value === null) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'string') return "'" + value.replace(/'/g, "\\'") + "'";
  return String(value);
}

// Node.js export (tests on workstation) — n8n Code nodes ignore this block.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { validateAutodevContract, typeCheck, jsTypeName, pyRepr };
}
