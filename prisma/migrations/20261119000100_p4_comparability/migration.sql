BEGIN;
SET LOCAL search_path=pg_catalog;

-- Run only as the already identified owner. No role or catalog seed is
-- created here. Existing ACLs/defaults are prerequisites, never repaired here.
DO $$
DECLARE schema_oid oid; owner_oid oid; runtime_oid oid; defaults_safe boolean;
BEGIN
  SELECT n.oid,n.nspowner INTO schema_oid,owner_oid FROM pg_catalog.pg_namespace n WHERE n.nspname='app';
  SELECT r.oid INTO runtime_oid FROM pg_catalog.pg_roles r WHERE r.rolname='detector_runtime';
  IF owner_oid IS NULL OR runtime_oid IS NULL
      OR pg_catalog.pg_get_userbyid(owner_oid)<>current_user
      OR owner_oid=runtime_oid OR pg_catalog.pg_has_role(runtime_oid,owner_oid,'MEMBER') THEN
    RAISE EXCEPTION 'P4 migration requires the trusted app owner and separate runtime' USING ERRCODE='42501';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid=runtime_oid
      AND (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls OR r.rolreplication)) THEN
    RAISE EXCEPTION 'P4 runtime role is privileged' USING ERRCODE='42501';
  END IF;
  -- app is trusted only to its owner. Superusers already bypass these ACLs;
  -- their administration is a separate prerequisite, not a runtime privilege.
  -- Check PUBLIC/direct grants, inherited CREATE and NOINHERIT + SET ROLE.
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
      CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
      WHERE n.oid=schema_oid AND a.privilege_type='CREATE' AND a.grantee<>owner_oid)
      OR EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid<>owner_oid AND NOT r.rolsuper
        AND (pg_catalog.has_schema_privilege(r.oid,schema_oid,'CREATE')
          OR pg_catalog.pg_has_role(r.oid,owner_oid,'SET'))) THEN
    RAISE EXCEPTION 'P4 schema requires exclusive trusted ownership' USING ERRCODE='42501';
  END IF;
  -- Schema defaults are additive. Missing global ACL uses PostgreSQL's built-in
  -- PUBLIC EXECUTE default and must fail. An empty effective ACL must also fail:
  -- definer wrappers need owner EXECUTE to call their private invoker helper.
  SELECT COALESCE(pg_catalog.bool_and(a.grantee=owner_oid AND a.privilege_type='EXECUTE'),false)
    INTO defaults_safe FROM (
      SELECT a.* FROM pg_catalog.aclexplode(COALESCE((SELECT d.defaclacl FROM pg_catalog.pg_default_acl d
        WHERE d.defaclrole=owner_oid AND d.defaclnamespace=0 AND d.defaclobjtype='f'),
        pg_catalog.acldefault('f',owner_oid))) a
      UNION ALL SELECT a.* FROM pg_catalog.pg_default_acl d
        CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
        WHERE d.defaclrole=owner_oid AND d.defaclnamespace=schema_oid AND d.defaclobjtype='f'
    ) a;
  IF NOT defaults_safe THEN
    RAISE EXCEPTION 'P4 requires reviewed private function defaults with owner execution' USING ERRCODE='42501';
  END IF;
END $$;

-- Reject inherited/default grants to any untrusted role, rather than changing
-- global defaults. Dependencies must have the same trusted owner as app.
DO $$
DECLARE owner_oid oid; schema_oid oid;
BEGIN
  SELECT oid,nspowner INTO schema_oid,owner_oid FROM pg_catalog.pg_namespace WHERE nspname='app';
  IF current_user<>'detector_migrator' OR EXISTS (
    SELECT 1 FROM (
      SELECT a.* FROM pg_catalog.aclexplode(COALESCE((SELECT defaclacl FROM pg_catalog.pg_default_acl
        WHERE defaclrole=owner_oid AND defaclnamespace=0 AND defaclobjtype='r'),pg_catalog.acldefault('r',owner_oid))) a
      UNION ALL SELECT a.* FROM pg_catalog.pg_default_acl d CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
        WHERE d.defaclrole=owner_oid AND d.defaclnamespace=schema_oid AND d.defaclobjtype='r'
    ) acl WHERE grantee<>owner_oid
  ) OR EXISTS (SELECT 1 FROM pg_catalog.pg_proc WHERE oid IN (
      'app.p4_v1_checked_receipt(uuid)'::regprocedure,'app.p4_v1_context()'::regprocedure,
      'app.observe_source(text,text,uuid,uuid,text,text,text,text,jsonb,text)'::regprocedure,
      'app.require_read_committed()'::regprocedure,'app.deny_mutation()'::regprocedure)
    AND proowner<>owner_oid) THEN
    RAISE EXCEPTION 'Untrusted comparability installation context' USING ERRCODE='42501';
  END IF;
END $$;

CREATE TABLE app.p4_comparability_definitions (
  kind text NOT NULL,
  definition_id text NOT NULL,
  definition_version text NOT NULL,
  declared_value jsonb NOT NULL,
  original_text text NOT NULL,
  text_sha256 text NOT NULL,
  CONSTRAINT p4_cmp_definitions_pk PRIMARY KEY (kind,definition_id,definition_version),
  CONSTRAINT p4_cmp_definitions_check CHECK (
    kind IN ('specification','packaging','price_basis','delivery','quantity_pricing')
    AND length(definition_id) BETWEEN 1 AND 200 AND length(definition_version) BETWEEN 1 AND 200
    AND jsonb_typeof(declared_value)='object' AND octet_length(original_text) BETWEEN 1 AND 16000
    AND text_sha256=encode(sha256(convert_to(original_text,'UTF8')),'hex'))
);

CREATE TABLE app.p4_comparability_revisions (
  id uuid NOT NULL,
  purchase_id uuid NOT NULL,
  purchase_version_id uuid NOT NULL,
  purchase_hash text NOT NULL,
  revision integer NOT NULL,
  previous_id uuid,
  previous_revision integer,
  previous_hash text,
  canonical_content text NOT NULL,
  content_sha256 text NOT NULL,
  definitions jsonb NOT NULL,
  source_reference_id uuid NOT NULL,
  actor_user_id uuid NOT NULL,
  recorded_at timestamptz(3) NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT p4_cmp_revisions_pk PRIMARY KEY (id),
  CONSTRAINT p4_cmp_purchase_revision_key UNIQUE (purchase_id,revision),
  CONSTRAINT p4_cmp_predecessor_key UNIQUE (previous_id),
  CONSTRAINT p4_cmp_source_key UNIQUE (source_reference_id),
  CONSTRAINT p4_cmp_chain_key UNIQUE (id,purchase_id,revision,content_sha256),
  CONSTRAINT p4_cmp_purchase_fk FOREIGN KEY (purchase_id) REFERENCES app.purchase_order_lines(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT p4_cmp_version_fk FOREIGN KEY (purchase_version_id,purchase_id) REFERENCES app.record_versions(id,purchase_line_owner_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT p4_cmp_previous_fk FOREIGN KEY (previous_id,purchase_id,previous_revision,previous_hash)
    REFERENCES app.p4_comparability_revisions(id,purchase_id,revision,content_sha256) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT p4_cmp_source_fk FOREIGN KEY (source_reference_id) REFERENCES app.source_references(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT p4_cmp_actor_fk FOREIGN KEY (actor_user_id) REFERENCES app.users(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT p4_cmp_revision_check CHECK (revision>0 AND (
    (revision=1 AND num_nonnulls(previous_id,previous_revision,previous_hash)=0) OR
    (revision>1 AND num_nonnulls(previous_id,previous_revision,previous_hash)=3 AND previous_revision=revision-1 AND previous_id<>id))),
  CONSTRAINT p4_cmp_content_check CHECK (purchase_hash ~ '^[0-9a-f]{64}$'
    AND octet_length(canonical_content) BETWEEN 1 AND 65536 AND jsonb_typeof(definitions)='object'
    AND content_sha256=encode(sha256(convert_to(canonical_content,'UTF8')),'hex') AND isfinite(recorded_at))
);
CREATE INDEX p4_cmp_version_idx ON app.p4_comparability_revisions(purchase_version_id);
CREATE INDEX p4_cmp_actor_idx ON app.p4_comparability_revisions(actor_user_id);
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON app.p4_comparability_definitions
  FOR EACH ROW EXECUTE FUNCTION app.deny_mutation();
CREATE TRIGGER preserve_table BEFORE TRUNCATE ON app.p4_comparability_definitions
  FOR EACH STATEMENT EXECUTE FUNCTION app.deny_mutation();
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON app.p4_comparability_revisions
  FOR EACH ROW EXECUTE FUNCTION app.deny_mutation();
CREATE TRIGGER preserve_table BEFORE TRUNCATE ON app.p4_comparability_revisions
  FOR EACH STATEMENT EXECUTE FUNCTION app.deny_mutation();

CREATE FUNCTION app.p4_cmp_assert(p_ok boolean) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
BEGIN
  IF p_ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Invalid comparability declaration' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION app.p4_cmp_shape(p_value jsonb,p_required text[],p_optional text[]) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
BEGIN
  IF pg_catalog.jsonb_typeof(p_value) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  RETURN p_value ?& p_required AND NOT EXISTS (
    SELECT 1 FROM pg_catalog.jsonb_object_keys(p_value) k WHERE NOT(k=ANY(p_required || p_optional)));
END $$;

CREATE FUNCTION app.p4_cmp_text(p_value jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
  SELECT pg_catalog.jsonb_typeof(p_value)='string' AND pg_catalog.length(p_value#>>'{}') BETWEEN 1 AND 200
    AND (p_value#>>'{}') !~ '[[:cntrl:]]' AND (p_value#>>'{}') !~ '^[[:space:]]|[[:space:]]$'
$$;

CREATE FUNCTION app.p4_cmp_canonical(p_value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE result text;
BEGIN
  CASE pg_catalog.jsonb_typeof(p_value)
    WHEN 'object' THEN
      SELECT '{' || COALESCE(pg_catalog.string_agg(pg_catalog.to_jsonb(key)::text || ':' || app.p4_cmp_canonical(value),',' ORDER BY key COLLATE "C"),'') || '}'
        INTO result FROM pg_catalog.jsonb_each(p_value); RETURN result;
    WHEN 'number' THEN RETURN pg_catalog.trim_scale((p_value#>>'{}')::numeric)::text;
    WHEN 'string' THEN RETURN p_value::text;
    WHEN 'null' THEN RETURN 'null';
    ELSE RAISE EXCEPTION 'Unsupported comparability JSON' USING ERRCODE='22023';
  END CASE;
END $$;

CREATE FUNCTION app.p4_cmp_validate(p_content jsonb,p_receipt jsonb,p_now timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE k text; entry jsonb; v jsonb; prov jsonb; purchase jsonb; stamp timestamptz;
  allowed text[]:=ARRAY['specification','unit','packaging','currency','price_basis','payment_days','delivery','quantity_pricing'];
BEGIN
  PERFORM app.p4_cmp_assert(app.p4_cmp_shape(p_content,ARRAY['contract','id','revision','supersedes','purchase','attributes'],ARRAY[]::text[]));
  PERFORM app.p4_cmp_assert(p_content->>'contract'='p4-manual-comparability/1.0'
    AND pg_catalog.jsonb_typeof(p_content->'id')='string'
    AND (p_content->>'id') ~ '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
    AND pg_catalog.jsonb_typeof(p_content->'revision')='number'
    AND (p_content->>'revision') ~ '^[1-9][0-9]*$' AND (p_content->>'revision')::numeric<=2147483647);
  PERFORM app.p4_cmp_assert(app.p4_cmp_shape(p_content->'purchase',ARRAY['id','version_id','content_sha256'],ARRAY[]::text[]));
  PERFORM app.p4_cmp_assert(p_receipt IS NOT NULL AND p_content->'purchase'=pg_catalog.jsonb_build_object(
    'id',p_receipt->>'id','version_id',p_receipt->>'version_id','content_sha256',p_receipt->>'content_hash'));
  IF (p_content->>'revision')::integer=1 THEN PERFORM app.p4_cmp_assert(p_content->'supersedes'='null'::jsonb);
  ELSE
    v:=p_content->'supersedes';
    PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['id','revision','content_sha256'],ARRAY[]::text[]));
    PERFORM app.p4_cmp_assert(pg_catalog.jsonb_typeof(v->'id')='string' AND pg_catalog.jsonb_typeof(v->'content_sha256')='string'
      AND (v->>'id') ~ '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
      AND v->>'id'<>p_content->>'id' AND (v->>'content_sha256') ~ '^[0-9a-f]{64}$'
      AND pg_catalog.jsonb_typeof(v->'revision')='number' AND (v->>'revision')::numeric=(p_content->>'revision')::integer-1);
  END IF;
  purchase:=p_receipt#>'{original_content,purchase}';
  PERFORM app.p4_cmp_assert(app.p4_cmp_shape(p_content->'attributes',ARRAY[]::text[],allowed));
  FOR k,entry IN SELECT key,value FROM pg_catalog.jsonb_each(p_content->'attributes') LOOP
    PERFORM app.p4_cmp_assert(app.p4_cmp_shape(entry,ARRAY['value','provenance'],ARRAY[]::text[]));
    prov:=entry->'provenance'; v:=entry->'value';
    PERFORM app.p4_cmp_assert(app.p4_cmp_shape(prov,ARRAY['kind','actor_id','declared_at'],ARRAY['evidence_ref']));
    PERFORM app.p4_cmp_assert(prov->>'kind'='declared' AND app.p4_cmp_text(prov->'actor_id')
      AND (NOT(prov ? 'evidence_ref') OR app.p4_cmp_text(prov->'evidence_ref'))
      AND (prov->>'declared_at') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{3}Z$');
    stamp:=app.exact_instant(prov->>'declared_at');
    PERFORM app.p4_cmp_assert(stamp<=p_now AND pg_catalog.to_char(stamp AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')=prov->>'declared_at');
    CASE k
      WHEN 'specification' THEN
        PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['id','version','product_id','sha256'],ARRAY[]::text[])
          AND app.p4_cmp_text(v->'id') AND app.p4_cmp_text(v->'version') AND v->>'product_id'=purchase#>>'{product,id}'
          AND pg_catalog.jsonb_typeof(v->'sha256')='string' AND (v->>'sha256') ~ '^[0-9a-f]{64}$');
      WHEN 'unit' THEN PERFORM app.p4_cmp_assert(v=purchase#>'{product,unit}');
      WHEN 'currency' THEN PERFORM app.p4_cmp_assert(v='"BRL"'::jsonb AND v=purchase->'currency');
      WHEN 'payment_days' THEN PERFORM app.p4_cmp_assert(v=purchase->'payment_days');
      WHEN 'packaging' THEN
        PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['id','version','quantity_per_package','content_unit'],ARRAY[]::text[])
          AND app.p4_cmp_text(v->'id') AND app.p4_cmp_text(v->'version') AND app.p4_cmp_text(v->'content_unit')
          AND pg_catalog.jsonb_typeof(v->'quantity_per_package')='string'
          AND (v->>'quantity_per_package') ~ '^(0|[1-9][0-9]{0,8})([.][0-9]{1,6})?$');
        PERFORM app.p4_cmp_assert((v->>'quantity_per_package')::numeric>0);
      WHEN 'price_basis' THEN
        PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['id','version','discounts','taxes','tax_credits','freight','other_charges'],ARRAY[]::text[])
          AND app.p4_cmp_text(v->'id') AND app.p4_cmp_text(v->'version')
          AND v->>'discounts' IN ('deducted','not_deducted','not_applicable') AND v->>'taxes' IN ('included','excluded')
          AND v->>'tax_credits' IN ('none','deducted','not_deducted') AND v->>'freight' IN ('included','excluded','not_applicable')
          AND v->>'other_charges' IN ('included','excluded','not_applicable'));
      WHEN 'delivery' THEN
        PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['condition_id','condition_version','location_id'],ARRAY[]::text[])
          AND app.p4_cmp_text(v->'condition_id') AND app.p4_cmp_text(v->'condition_version') AND app.p4_cmp_text(v->'location_id'));
      WHEN 'quantity_pricing' THEN
        IF v->>'regime' IN ('same_quantity_only','quantity_independent') THEN
          PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['regime'],ARRAY[]::text[]));
        ELSE
          PERFORM app.p4_cmp_assert(app.p4_cmp_shape(v,ARRAY['regime','schedule_id','schedule_version','min_quantity','max_quantity'],ARRAY[]::text[])
            AND v->>'regime'='tier' AND app.p4_cmp_text(v->'schedule_id') AND app.p4_cmp_text(v->'schedule_version')
            AND pg_catalog.jsonb_typeof(v->'min_quantity')='number' AND pg_catalog.jsonb_typeof(v->'max_quantity')='number'
            AND (v->>'min_quantity') ~ '^[1-9][0-9]*$' AND (v->>'max_quantity') ~ '^[1-9][0-9]*$');
          PERFORM app.p4_cmp_assert((v->>'min_quantity')::numeric<= (purchase->>'quantity')::numeric
            AND (v->>'max_quantity')::numeric >= (purchase->>'quantity')::numeric AND (v->>'max_quantity')::numeric<=1000000);
        END IF;
    END CASE;
  END LOOP;
END $$;

CREATE FUNCTION app.p4_cmp_definition_key(p_kind text,p_value jsonb) RETURNS text[]
LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
  SELECT CASE p_kind WHEN 'delivery' THEN ARRAY[p_value->>'condition_id',p_value->>'condition_version']
    WHEN 'quantity_pricing' THEN ARRAY[p_value->>'schedule_id',p_value->>'schedule_version']
    ELSE ARRAY[p_value->>'id',p_value->>'version'] END
$$;

CREATE FUNCTION app.p4_cmp_definitions(p_content jsonb,p_definitions jsonb) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE keys text[]:=ARRAY[]::text[]; k text; v jsonb;
BEGIN
  FOREACH k IN ARRAY ARRAY['specification','packaging','price_basis','delivery','quantity_pricing'] LOOP
    v:=p_content#>ARRAY['attributes',k,'value'];
    IF v IS NOT NULL AND (k<>'quantity_pricing' OR v->>'regime'='tier') THEN keys:=pg_catalog.array_append(keys,k); END IF;
  END LOOP;
  PERFORM app.p4_cmp_assert(app.p4_cmp_shape(p_definitions,keys,ARRAY[]::text[]));
  FOREACH k IN ARRAY keys LOOP
    PERFORM app.p4_cmp_assert(pg_catalog.jsonb_typeof(p_definitions->k)='string'
      AND pg_catalog.octet_length(p_definitions->>k) BETWEEN 1 AND 16000 AND pg_catalog.btrim(p_definitions->>k)<>'');
    IF k='specification' THEN PERFORM app.p4_cmp_assert(
      pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_definitions->>k,'UTF8')),'hex')=p_content#>>'{attributes,specification,value,sha256}'); END IF;
  END LOOP;
END $$;

CREATE FUNCTION app.p4_cmp_pack(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE r app.p4_comparability_revisions%ROWTYPE; receipt jsonb; content jsonb; k text; key_parts text[]; v jsonb;
BEGIN
  SELECT * INTO r FROM app.p4_comparability_revisions WHERE id=p_id;
  IF NOT FOUND THEN RETURN NULL; END IF;
  receipt:=app.p4_v1_checked_receipt(r.purchase_id); content:=r.canonical_content::jsonb;
  PERFORM app.p4_cmp_validate(content,receipt,r.recorded_at); PERFORM app.p4_cmp_definitions(content,r.definitions);
  IF content->>'id' IS DISTINCT FROM r.id::text OR (content->>'revision')::integer IS DISTINCT FROM r.revision
      OR content#>>'{purchase,version_id}' IS DISTINCT FROM r.purchase_version_id::text
      OR content#>>'{purchase,content_sha256}' IS DISTINCT FROM r.purchase_hash
      OR content#>>'{supersedes,id}' IS DISTINCT FROM r.previous_id::text
      OR content#>>'{supersedes,content_sha256}' IS DISTINCT FROM r.previous_hash
      OR (content#>>'{supersedes,revision}')::integer IS DISTINCT FROM r.previous_revision
      OR r.canonical_content IS DISTINCT FROM app.p4_cmp_canonical(content)
      OR r.content_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(r.canonical_content,'UTF8')),'hex')
      OR NOT EXISTS (SELECT 1 FROM app.source_references s JOIN app.audit_events a ON a.source_reference_id=s.id
        WHERE s.id=r.source_reference_id AND s.source_namespace='p4-comparability/1.0' AND s.source_entity_kind='purchase_order_line'
          AND s.source_identity_id IS NULL AND s.source_version='p4-manual-comparability/1.0' AND s.source_record_key=r.id::text
          AND s.original_content=pg_catalog.jsonb_build_object('content',content,'definitions',r.definitions)
          AND s.content_hash=r.content_sha256 AND s.available_at IS NULL AND s.availability_status='unverified'
          AND a.operation='source_observe' AND a.actor_user_id=r.actor_user_id) THEN
    RAISE EXCEPTION 'Comparability integrity' USING ERRCODE='23514';
  END IF;
  FOR k IN SELECT pg_catalog.jsonb_object_keys(r.definitions) LOOP
    v:=content#>ARRAY['attributes',k,'value']; key_parts:=app.p4_cmp_definition_key(k,v);
    IF k='delivery' THEN v:=v-'location_id';
    ELSIF k='quantity_pricing' THEN v:=v-'min_quantity'-'max_quantity'; END IF;
    IF NOT EXISTS (SELECT 1 FROM app.p4_comparability_definitions d WHERE d.kind=k
        AND d.definition_id=key_parts[1] AND d.definition_version=key_parts[2]
        AND d.declared_value=v AND d.original_text=r.definitions->>k) THEN
      RAISE EXCEPTION 'Comparability definition integrity' USING ERRCODE='23514';
    END IF;
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('canonical_content',r.canonical_content,'content_sha256',r.content_sha256,
    'definitions',r.definitions,'recorded_at',pg_catalog.to_char(r.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
    'source_reference_id',r.source_reference_id,'actor_user_id',r.actor_user_id);
EXCEPTION WHEN invalid_parameter_value OR invalid_text_representation OR datetime_field_overflow
    OR invalid_datetime_format OR numeric_value_out_of_range THEN
  RAISE EXCEPTION 'Comparability stored integrity' USING ERRCODE='23514';
END $$;

CREATE FUNCTION app.p4_cmp_write(p_canonical text,p_definitions jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE content jsonb; receipt jsonb; purchase uuid; new_id uuid; head app.p4_comparability_revisions%ROWTYPE;
  existing app.p4_comparability_revisions%ROWTYPE; k text; v jsonb; key_parts text[];
  actor uuid; source uuid; digest text; stamp timestamptz(3);
BEGIN
  PERFORM app.require_read_committed();
  PERFORM app.p4_cmp_assert(p_canonical IS NOT NULL AND pg_catalog.octet_length(p_canonical) BETWEEN 1 AND 65536);
  content:=p_canonical::jsonb;
  -- Lock the EXISTING parent, not an absent metadata row. This serializes the
  -- first revision as well as subsequent revisions. Never modify that parent.
  purchase:=(content#>>'{purchase,id}')::uuid;
  PERFORM 1 FROM app.purchase_order_lines WHERE id=purchase FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Purchase not found' USING ERRCODE='23503'; END IF;
  receipt:=app.p4_v1_checked_receipt(purchase);
  stamp:=pg_catalog.clock_timestamp();
  PERFORM app.p4_cmp_validate(content,receipt,stamp); PERFORM app.p4_cmp_definitions(content,p_definitions);
  PERFORM app.p4_cmp_assert(p_canonical=app.p4_cmp_canonical(content));
  new_id:=(content->>'id')::uuid;
  digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_canonical,'UTF8')),'hex');
  SELECT * INTO existing FROM app.p4_comparability_revisions WHERE id=new_id;
  IF FOUND THEN
    IF existing.purchase_id<>purchase OR existing.canonical_content<>p_canonical OR existing.definitions<>p_definitions THEN
      RAISE EXCEPTION 'Comparability revision conflict' USING ERRCODE='23505';
    END IF;
    RETURN pg_catalog.jsonb_build_object('contract','p4-comparability-storage/1.0','outcome','replay','revision',app.p4_cmp_pack(new_id));
  END IF;
  SELECT * INTO head FROM app.p4_comparability_revisions WHERE purchase_id=purchase ORDER BY revision DESC LIMIT 1;
  IF ((head.id IS NULL) AND (content->>'revision')::integer<>1) OR
      (head.id IS NOT NULL AND ((content->>'revision')::integer<>head.revision+1
        OR content#>>'{supersedes,id}' IS DISTINCT FROM head.id::text
        OR content#>>'{supersedes,content_sha256}' IS DISTINCT FROM head.content_sha256)) THEN
    RAISE EXCEPTION 'Comparability predecessor conflict' USING ERRCODE='23505';
  END IF;
  -- Deterministic lock order across definitions. ON CONFLICT waits for another
  -- purchase's definition insert; the following statement checks its committed
  -- value under READ COMMITTED. Definitions are NEVER updated on conflict.
  FOR k IN SELECT key FROM pg_catalog.jsonb_object_keys(p_definitions) AS keys(key) ORDER BY key COLLATE "C" LOOP
    v:=content#>ARRAY['attributes',k,'value']; key_parts:=app.p4_cmp_definition_key(k,v);
    -- A delivery condition can serve multiple sites; one schedule can contain
    -- multiple tiers. Per-purchase site/bounds remain in immutable content.
    IF k='delivery' THEN v:=v-'location_id';
    ELSIF k='quantity_pricing' THEN v:=v-'min_quantity'-'max_quantity'; END IF;
    INSERT INTO app.p4_comparability_definitions(kind,definition_id,definition_version,declared_value,original_text,text_sha256)
      VALUES(k,key_parts[1],key_parts[2],v,p_definitions->>k,pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_definitions->>k,'UTF8')),'hex'))
      ON CONFLICT (kind,definition_id,definition_version) DO NOTHING;
    IF NOT EXISTS (SELECT 1 FROM app.p4_comparability_definitions d WHERE d.kind=k
        AND d.definition_id=key_parts[1] AND d.definition_version=key_parts[2]
        AND d.declared_value=v AND d.original_text=p_definitions->>k) THEN
      RAISE EXCEPTION 'Comparability definition version conflict' USING ERRCODE='23505';
    END IF;
  END LOOP;
  actor:=(app.p4_v1_context()#>>'{actor,id}')::uuid;
  source:=app.observe_source('p4-comparability/1.0','purchase_order_line',actor,NULL,
    'p4-manual-comparability/1.0',new_id::text,NULL,digest,
    pg_catalog.jsonb_build_object('content',content,'definitions',p_definitions),NULL);
  INSERT INTO app.p4_comparability_revisions(id,purchase_id,purchase_version_id,purchase_hash,revision,
      previous_id,previous_revision,previous_hash,canonical_content,content_sha256,definitions,source_reference_id,actor_user_id,recorded_at)
    VALUES(new_id,purchase,(content#>>'{purchase,version_id}')::uuid,content#>>'{purchase,content_sha256}',(content->>'revision')::integer,
      (content#>>'{supersedes,id}')::uuid,(content#>>'{supersedes,revision}')::integer,content#>>'{supersedes,content_sha256}',
      p_canonical,digest,p_definitions,source,actor,stamp);
  RETURN pg_catalog.jsonb_build_object('contract','p4-comparability-storage/1.0','outcome','created','revision',app.p4_cmp_pack(new_id));
END $$;

CREATE FUNCTION app.p4_cmp_read(p_purchase uuid,p_revision integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE receipt jsonb; selected uuid;
BEGIN
  PERFORM app.p4_cmp_assert(p_purchase IS NOT NULL AND (p_revision IS NULL OR p_revision>0));
  receipt:=app.p4_v1_checked_receipt(p_purchase);
  IF receipt IS NULL THEN RAISE EXCEPTION 'Purchase not found' USING ERRCODE='23503'; END IF;
  SELECT id INTO selected FROM app.p4_comparability_revisions WHERE purchase_id=p_purchase
    AND (p_revision IS NULL OR revision=p_revision) ORDER BY revision DESC LIMIT 1;
  RETURN pg_catalog.jsonb_build_object('contract','p4-comparability-storage/1.0',
    'outcome',CASE WHEN selected IS NULL THEN 'absent' ELSE 'found' END,'revision',app.p4_cmp_pack(selected));
END $$;

REVOKE ALL ON TABLE app.p4_comparability_definitions,app.p4_comparability_revisions FROM PUBLIC,detector_runtime;
REVOKE ALL ON FUNCTION app.p4_cmp_assert(boolean),app.p4_cmp_shape(jsonb,text[],text[]),app.p4_cmp_text(jsonb),
  app.p4_cmp_canonical(jsonb),app.p4_cmp_validate(jsonb,jsonb,timestamptz),app.p4_cmp_definition_key(text,jsonb),
  app.p4_cmp_definitions(jsonb,jsonb),app.p4_cmp_pack(uuid),app.p4_cmp_write(text,jsonb),app.p4_cmp_read(uuid,integer)
  FROM PUBLIC,detector_runtime;
GRANT EXECUTE ON FUNCTION app.p4_cmp_write(text,jsonb),app.p4_cmp_read(uuid,integer) TO detector_runtime;
COMMIT;

