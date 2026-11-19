BEGIN;
SET LOCAL search_path=pg_catalog;

-- Run only as the already identified owner. No role, table or catalog seed is
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
      AND (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls)) THEN
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

CREATE FUNCTION app.p4_v1_context() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE actor uuid; currency uuid; mapped uuid; item record;
  suppliers jsonb:='[]'::jsonb; departments jsonb:='[]'::jsonb;
BEGIN
  SELECT u.id INTO actor FROM app.users u
    WHERE u.auth_issuer='p4-demo' AND u.auth_subject='manual-purchase-service' AND u.is_active;
  SELECT c.id INTO currency FROM app.currencies c WHERE c.code='BRL';
  IF actor IS NULL OR currency IS NULL THEN
    RAISE EXCEPTION 'P4 context unavailable' USING ERRCODE='55000';
  END IF;
  FOR item IN SELECT * FROM (VALUES
      ('sup-obra','Obra Exemplo — materiais de construção'),
      ('sup-base','Base Exemplo — suprimentos'),
      ('sup-estrutura','Estrutura Exemplo — materiais')) AS catalog(code,label) ORDER BY code LOOP
    SELECT s.id INTO mapped FROM app.source_identities i JOIN app.suppliers s ON s.id=i.supplier_id
      WHERE i.source_namespace='p4-catalog/1.0' AND i.source_entity_kind='supplier'
        AND i.source_id=item.code AND i.resolved_at IS NOT NULL AND s.name=item.label;
    IF mapped IS NULL THEN RAISE EXCEPTION 'P4 context unavailable' USING ERRCODE='55000'; END IF;
    suppliers:=suppliers || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('source_id',item.code,'id',mapped));
  END LOOP;
  FOR item IN SELECT * FROM (VALUES
      ('dep-obras','Obras'),('dep-manutencao','Manutenção'),('dep-almoxarifado','Almoxarifado'))
      AS catalog(code,label) ORDER BY code LOOP
    SELECT d.id INTO mapped FROM app.source_identities i JOIN app.departments d ON d.id=i.department_id
      WHERE i.source_namespace='p4-catalog/1.0' AND i.source_entity_kind='department'
        AND i.source_id=item.code AND i.resolved_at IS NOT NULL AND d.name=item.label;
    IF mapped IS NULL THEN RAISE EXCEPTION 'P4 context unavailable' USING ERRCODE='55000'; END IF;
    departments:=departments || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('source_id',item.code,'id',mapped));
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('contract','p4-storage/1.0','catalog_version','p4-catalog/1.0',
    'actor',pg_catalog.jsonb_build_object('id',actor,'issuer','p4-demo','subject','manual-purchase-service'),
    'currency',pg_catalog.jsonb_build_object('id',currency,'code','BRL'),
    'suppliers',suppliers,'departments',departments);
END $$;

-- Private validator reused by the three receipt readers. No runtime grant.
-- NULL means a UUID outside P4. An existing but inconsistent P4 identity fails
-- closed instead of becoming an absent receipt or exposing arbitrary JSON.
CREATE FUNCTION app.p4_v1_checked_receipt(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE identity_row app.source_identities%ROWTYPE; version_row app.record_versions%ROWTYPE;
  reference_row app.source_references%ROWTYPE; count_id bigint; purchase jsonb; expected jsonb;
  supplier_name text; department_name text; product_name text; product_unit text;
  quantity_value numeric; days_value numeric; price_value numeric; total_value numeric;
BEGIN
  IF p_id IS NULL THEN RAISE EXCEPTION 'Invalid P4 identifier' USING ERRCODE='22023'; END IF;
  SELECT pg_catalog.count(*) INTO count_id FROM app.source_identities i
    WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line'
      AND i.purchase_order_line_id=p_id;
  IF count_id=0 THEN
    IF EXISTS (SELECT 1 FROM app.record_versions v JOIN app.source_references r ON r.id=v.source_reference_id
        WHERE v.purchase_line_owner_id=p_id AND v.revision_no=1
          AND r.source_namespace='p4-manual/1.0' AND r.source_entity_kind='purchase_order_line') THEN
      RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
  END IF;
  IF count_id<>1 THEN RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514'; END IF;
  SELECT i.* INTO identity_row FROM app.source_identities i
    WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line'
      AND i.purchase_order_line_id=p_id;
  IF identity_row.resolved_at IS NULL OR identity_row.supplier_id IS NOT NULL
      OR identity_row.department_id IS NOT NULL
      OR identity_row.source_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  SELECT v.* INTO version_row FROM app.record_versions v
    JOIN app.purchase_order_lines l ON l.id=v.purchase_line_owner_id
    WHERE l.id=p_id AND v.revision_no=1;
  IF NOT FOUND OR version_row.supplier_owner_id IS NOT NULL OR version_row.department_owner_id IS NOT NULL
      OR version_row.supersedes_version_id IS NOT NULL OR version_row.payload_schema<>1
      OR version_row.source_reference_id IS NULL THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  SELECT r.* INTO reference_row FROM app.source_references r WHERE r.id=version_row.source_reference_id;
  IF NOT FOUND OR reference_row.source_identity_id IS NOT NULL
      OR reference_row.source_namespace IS DISTINCT FROM 'p4-manual/1.0'
      OR reference_row.source_entity_kind IS DISTINCT FROM 'purchase_order_line'
      OR reference_row.source_version IS DISTINCT FROM 'p4-purchase/1.0'
      OR reference_row.source_record_key IS DISTINCT FROM identity_row.source_id
      OR reference_row.content_hash IS NULL OR reference_row.content_hash !~ '^[0-9a-f]{64}$'
      OR reference_row.locator IS NOT NULL OR reference_row.available_at IS NOT NULL
      OR reference_row.availability_status IS DISTINCT FROM 'unverified' THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  purchase:=reference_row.original_content->'purchase';
  -- Validate types before casts. Exact reconstructed JSON equality below rejects
  -- unknown fields and catalog content, including nested fields.
  IF pg_catalog.jsonb_typeof(purchase) IS DISTINCT FROM 'object'
      OR pg_catalog.jsonb_typeof(purchase->'quantity') IS DISTINCT FROM 'number'
      OR pg_catalog.jsonb_typeof(purchase->'payment_days') IS DISTINCT FROM 'number'
      OR pg_catalog.jsonb_typeof(purchase->'unit_price') IS DISTINCT FROM 'string'
      OR pg_catalog.jsonb_typeof(purchase->'total') IS DISTINCT FROM 'string'
      OR pg_catalog.jsonb_typeof(purchase->'purchase_date') IS DISTINCT FROM 'string'
      OR (purchase->>'unit_price') !~ '^(0|[1-9][0-9]{0,6})[.][0-9]{2}$'
      OR (purchase->>'total') !~ '^(0|[1-9][0-9]{0,12})[.][0-9]{2}$' THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  quantity_value:=(purchase->>'quantity')::numeric; days_value:=(purchase->>'payment_days')::numeric;
  price_value:=(purchase->>'unit_price')::numeric; total_value:=(purchase->>'total')::numeric;
  IF quantity_value<>pg_catalog.trunc(quantity_value) OR quantity_value NOT BETWEEN 1 AND 1000000
      OR days_value<>pg_catalog.trunc(days_value) OR days_value NOT BETWEEN 0 AND 3650
      OR price_value<=0 OR price_value>1000000 OR total_value<>quantity_value*price_value THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  SELECT label INTO supplier_name FROM (VALUES
      ('sup-obra','Obra Exemplo — materiais de construção'),
      ('sup-base','Base Exemplo — suprimentos'),('sup-estrutura','Estrutura Exemplo — materiais'))
    AS catalog(code,label) WHERE code=purchase#>>'{supplier,id}';
  SELECT label INTO department_name FROM (VALUES
      ('dep-obras','Obras'),('dep-manutencao','Manutenção'),('dep-almoxarifado','Almoxarifado'))
    AS catalog(code,label) WHERE code=purchase#>>'{department,id}';
  SELECT label,unit INTO product_name,product_unit FROM (VALUES
      ('prod-cimento','Cimento CP II · saco de 50 kg','saco de 50 kg'),
      ('prod-tijolo','Tijolo cerâmico · unidade','unidade'),
      ('prod-vergalhao','Vergalhão de aço · barra de 12 m','barra de 12 m'),
      ('prod-argamassa','Argamassa · saco de 20 kg','saco de 20 kg'),
      ('prod-tubo','Tubo PVC · barra de 6 m','barra de 6 m')) AS catalog(code,label,unit)
    WHERE code=purchase#>>'{product,id}';
  IF supplier_name IS NULL OR department_name IS NULL OR product_name IS NULL THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  expected:=pg_catalog.jsonb_build_object('contract','p4-purchase/1.0','origin','manual',
    'catalog_version','p4-catalog/1.0','catalog_origin','synthetic',
    'purchase',pg_catalog.jsonb_build_object(
      'supplier',pg_catalog.jsonb_build_object('id',purchase#>>'{supplier,id}','name',supplier_name),
      'product',pg_catalog.jsonb_build_object('id',purchase#>>'{product,id}','name',product_name,'unit',product_unit),
      'department',pg_catalog.jsonb_build_object('id',purchase#>>'{department,id}','name',department_name),
      'quantity',quantity_value,'unit_price',purchase->>'unit_price','total',purchase->>'total',
      'currency','BRL','purchase_date',purchase->>'purchase_date','payment_days',days_value));
  IF reference_row.original_content IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  BEGIN
    -- P4.2 rejects future commercial dates. For an immutable receipt, use the
    -- revision's registration day, not today's date or the session timezone.
    IF NOT pg_catalog.isfinite(version_row.recorded_at)
        OR app.exact_date(purchase->>'purchase_date') > (version_row.recorded_at AT TIME ZONE 'America/Sao_Paulo')::date THEN
      RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
    END IF;
    expected:=app.normalize_payload('purchase_order_line',pg_catalog.jsonb_build_object(
      'description',product_name,'po_date',purchase->>'purchase_date',
      'quantity',quantity_value::text,'unit_price',purchase->>'unit_price','amount',purchase->>'total'));
  EXCEPTION WHEN invalid_parameter_value OR numeric_value_out_of_range OR invalid_text_representation THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END;
  IF version_row.payload IS DISTINCT FROM expected
      OR NOT EXISTS (SELECT 1 FROM app.currencies c WHERE c.id=version_row.currency_id AND c.code='BRL')
      OR NOT EXISTS (SELECT 1 FROM app.source_identities i JOIN app.suppliers s ON s.id=i.supplier_id
        WHERE i.source_namespace='p4-catalog/1.0' AND i.source_entity_kind='supplier'
          AND i.source_id=purchase#>>'{supplier,id}' AND i.resolved_at IS NOT NULL
          AND i.supplier_id=version_row.supplier_id)
      OR NOT EXISTS (SELECT 1 FROM app.source_identities i JOIN app.departments d ON d.id=i.department_id
        WHERE i.source_namespace='p4-catalog/1.0' AND i.source_entity_kind='department'
          AND i.source_id=purchase#>>'{department,id}' AND i.resolved_at IS NOT NULL
          AND i.department_id=version_row.department_id)
      OR NOT EXISTS (SELECT 1 FROM app.audit_events a WHERE a.operation='create'
        AND a.after_version_id=version_row.id AND a.before_version_id IS NULL
        AND a.actor_user_id=version_row.actor_user_id) THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  -- The hash was made from the P4.2 ordered JSON serialization. jsonb::text is
  -- NOT that serialization. The repository verifies the canonical hash again.
  RETURN pg_catalog.jsonb_build_object(
    'id',p_id,'version_id',version_row.id,'revision_no',version_row.revision_no,
    'recorded_at',pg_catalog.to_char(version_row.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
    'source_reference_id',reference_row.id,'source_identity_id',reference_row.source_identity_id,
    'source_namespace',identity_row.source_namespace,'source_entity_kind',identity_row.source_entity_kind,
    'source_id',identity_row.source_id,'reference_namespace',reference_row.source_namespace,
    'reference_kind',reference_row.source_entity_kind,'source_version',reference_row.source_version,
    'source_record_key',reference_row.source_record_key,'content_hash',reference_row.content_hash,
    'original_content',reference_row.original_content,'payload_schema',version_row.payload_schema,
    'state',version_row.payload,'currency_code','BRL','supplier_matches',true,'department_matches',true);
END $$;

CREATE FUNCTION app.p4_v1_receipt_by_key(p_key uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE identity_row app.source_identities%ROWTYPE; receipt jsonb;
BEGIN
  IF p_key IS NULL OR p_key::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'Invalid P4 key' USING ERRCODE='22023';
  END IF;
  SELECT i.* INTO identity_row FROM app.source_identities i
    WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line' AND i.source_id=p_key::text;
  IF NOT FOUND THEN
    IF EXISTS (SELECT 1 FROM app.source_references r WHERE r.source_namespace='p4-manual/1.0'
        AND r.source_entity_kind='purchase_order_line' AND r.source_record_key=p_key::text) THEN
      RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
    END IF;
    RETURN pg_catalog.jsonb_build_object('contract','p4-storage/1.0','status','absent','receipt',NULL);
  END IF;
  IF identity_row.resolved_at IS NULL OR identity_row.purchase_order_line_id IS NULL THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  receipt:=app.p4_v1_checked_receipt(identity_row.purchase_order_line_id);
  IF receipt IS NULL OR receipt->>'source_id' IS DISTINCT FROM p_key::text THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  RETURN pg_catalog.jsonb_build_object('contract','p4-storage/1.0','status','found','receipt',receipt);
END $$;

CREATE FUNCTION app.p4_v1_receipt_by_id(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE receipt jsonb;
BEGIN
  receipt:=app.p4_v1_checked_receipt(p_id);
  RETURN pg_catalog.jsonb_build_object('contract','p4-storage/1.0',
    'status',CASE WHEN receipt IS NULL THEN 'absent' ELSE 'found' END,'receipt',receipt);
END $$;

CREATE FUNCTION app.p4_v1_history(p_limit integer,p_after_time timestamptz,p_after_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app,pg_temp AS $$
DECLARE item record; receipt jsonb; items jsonb:='[]'::jsonb; next_cursor jsonb:=NULL;
  last_receipt jsonb; seen integer:=0;
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100
      OR (p_after_time IS NULL)<>(p_after_id IS NULL) THEN
    RAISE EXCEPTION 'Invalid P4 page' USING ERRCODE='22023';
  END IF;
  IF p_after_time IS NOT NULL AND (NOT pg_catalog.isfinite(p_after_time)
      OR p_after_time<>pg_catalog.date_trunc('milliseconds',p_after_time)
      OR p_after_time < TIMESTAMPTZ '0001-01-01 00:00:00+00'
      OR p_after_time >= TIMESTAMPTZ '10000-01-01 00:00:00+00') THEN
    RAISE EXCEPTION 'Invalid P4 page' USING ERRCODE='22023';
  END IF;
  -- Never silently discard a committed unresolved identity or missing revision.
  IF EXISTS (SELECT 1 FROM app.source_identities i
      LEFT JOIN app.record_versions v ON v.purchase_line_owner_id=i.purchase_order_line_id AND v.revision_no=1
      WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line'
        AND (i.resolved_at IS NULL OR i.purchase_order_line_id IS NULL OR v.id IS NULL)) THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  IF EXISTS (SELECT 1 FROM app.record_versions v JOIN app.source_references r ON r.id=v.source_reference_id
      WHERE v.revision_no=1 AND v.purchase_line_owner_id IS NOT NULL
        AND r.source_namespace='p4-manual/1.0' AND r.source_entity_kind='purchase_order_line'
        AND NOT EXISTS (SELECT 1 FROM app.source_identities i
          WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line'
            AND i.purchase_order_line_id=v.purchase_line_owner_id)) THEN
    RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514';
  END IF;
  FOR item IN SELECT v.purchase_line_owner_id AS id FROM app.record_versions v
      WHERE v.revision_no=1 AND EXISTS (SELECT 1 FROM app.source_identities i
        WHERE i.source_namespace='p4-manual/1.0' AND i.source_entity_kind='purchase_order_line'
          AND i.purchase_order_line_id=v.purchase_line_owner_id)
        AND (p_after_time IS NULL OR (v.recorded_at,v.purchase_line_owner_id)<(p_after_time,p_after_id))
      ORDER BY v.recorded_at DESC,v.purchase_line_owner_id DESC LIMIT p_limit+1 LOOP
    receipt:=app.p4_v1_checked_receipt(item.id);
    IF receipt IS NULL THEN RAISE EXCEPTION 'P4 receipt integrity' USING ERRCODE='23514'; END IF;
    seen:=seen+1;
    IF seen>p_limit THEN
      next_cursor:=pg_catalog.jsonb_build_object('recorded_at',last_receipt->>'recorded_at','id',last_receipt->>'id');
      EXIT;
    END IF;
    items:=items || pg_catalog.jsonb_build_array(receipt); last_receipt:=receipt;
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('contract','p4-storage/1.0','items',items,'next_cursor',next_cursor);
END $$;

-- Atomic installation: no window in which PUBLIC can execute a new function.
REVOKE ALL ON FUNCTION app.p4_v1_context(),app.p4_v1_checked_receipt(uuid),
  app.p4_v1_receipt_by_key(uuid),app.p4_v1_receipt_by_id(uuid),app.p4_v1_history(integer,timestamptz,uuid)
  FROM PUBLIC,detector_runtime;
GRANT EXECUTE ON FUNCTION app.p4_v1_context(),app.p4_v1_receipt_by_key(uuid),
  app.p4_v1_receipt_by_id(uuid),app.p4_v1_history(integer,timestamptz,uuid) TO detector_runtime;
COMMIT;
