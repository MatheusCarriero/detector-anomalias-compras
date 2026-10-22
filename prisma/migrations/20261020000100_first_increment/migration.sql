BEGIN;

-- Prisma Migrate may create app/_prisma_migrations before applying this file.
-- Accept only that bootstrap (or an empty namespace owned by this migrator).
-- Existing domain objects are an error, never silently reused.
SET LOCAL search_path=pg_catalog;
DO $$
DECLARE namespace_oid oid; metadata_oid oid; metadata_type oid; namespace_owner name;
BEGIN
  SELECT oid,pg_get_userbyid(nspowner) INTO namespace_oid,namespace_owner
    FROM pg_namespace WHERE nspname='app';
  IF namespace_oid IS NULL THEN
    CREATE SCHEMA app;
  ELSE
    IF namespace_owner<>current_user THEN
      RAISE EXCEPTION 'app must belong to the identified migration owner' USING ERRCODE='42501';
    END IF;
    SELECT oid,reltype INTO metadata_oid,metadata_type FROM pg_class
      WHERE relnamespace=namespace_oid AND relname='_prisma_migrations' AND relkind='r';
    IF EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace=namespace_oid
        AND c.oid IS DISTINCT FROM metadata_oid
        AND NOT EXISTS(SELECT 1 FROM pg_index i WHERE i.indexrelid=c.oid AND i.indrelid=metadata_oid))
      OR EXISTS(SELECT 1 FROM pg_proc WHERE pronamespace=namespace_oid)
      OR EXISTS(SELECT 1 FROM pg_type WHERE typnamespace=namespace_oid
        AND oid IS DISTINCT FROM metadata_type AND typelem IS DISTINCT FROM metadata_type) THEN
      RAISE EXCEPTION 'Unexpected preexisting objects in app; inspect without resetting' USING ERRCODE='55000';
    END IF;
  END IF;
END $$;
SET LOCAL search_path=app,pg_catalog;

-- CreateTable
CREATE TABLE "currencies" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "code" VARCHAR(3) NOT NULL,
    "name" TEXT NOT NULL,

    CONSTRAINT "currencies_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "departments" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "name" TEXT NOT NULL,
    "code" TEXT,
    "current_version_id" UUID NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "departments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "display_name" TEXT NOT NULL,
    "email" TEXT,
    "auth_issuer" TEXT,
    "auth_subject" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "department_id" UUID,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "suppliers" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "name" TEXT NOT NULL,
    "country_code" VARCHAR(2),
    "status" TEXT,
    "tier" TEXT,
    "current_version_id" UUID NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "suppliers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "purchase_order_lines" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "description" TEXT,
    "po_date" DATE,
    "supplier_id" UUID,
    "department_id" UUID,
    "currency_id" UUID,
    "quantity" DECIMAL(20,6),
    "unit_price" DECIMAL(24,8),
    "amount" DECIMAL(24,6),
    "current_version_id" UUID NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "purchase_order_lines_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "source_identities" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "source_namespace" TEXT NOT NULL,
    "source_entity_kind" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "supplier_id" UUID,
    "department_id" UUID,
    "purchase_order_line_id" UUID,
    "recorded_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolved_at" TIMESTAMPTZ(3),

    CONSTRAINT "source_identities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "source_references" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "source_identity_id" UUID,
    "source_namespace" TEXT NOT NULL,
    "source_entity_kind" TEXT NOT NULL,
    "source_version" TEXT,
    "source_record_key" TEXT,
    "locator" TEXT,
    "content_hash" VARCHAR(64),
    "original_content" JSONB,
    "recorded_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "available_at" TIMESTAMPTZ(3),
    "availability_status" TEXT NOT NULL DEFAULT 'unverified',

    CONSTRAINT "source_references_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "record_versions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "supplier_owner_id" UUID,
    "department_owner_id" UUID,
    "purchase_line_owner_id" UUID,
    "revision_no" INTEGER NOT NULL,
    "supersedes_version_id" UUID,
    "source_reference_id" UUID,
    "actor_user_id" UUID NOT NULL,
    "recorded_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "effective_from" TIMESTAMPTZ(3),
    "effective_to" TIMESTAMPTZ(3),
    "payload_schema" INTEGER NOT NULL DEFAULT 1,
    "payload" JSONB NOT NULL,
    "supplier_id" UUID,
    "department_id" UUID,
    "currency_id" UUID,

    CONSTRAINT "record_versions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "decision_snapshots" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "purpose" TEXT NOT NULL DEFAULT 'record_capture',
    "status" TEXT NOT NULL DEFAULT 'draft',
    "root_record_version_id" UUID NOT NULL,
    "actor_user_id" UUID NOT NULL,
    "knowledge_cutoff_at" TIMESTAMPTZ(3) NOT NULL,
    "captured_at" TIMESTAMPTZ(3) NOT NULL,
    "capture_mode" TEXT NOT NULL DEFAULT 'contemporaneous',
    "availability_status" TEXT NOT NULL DEFAULT 'captured_now',
    "hash_format" TEXT NOT NULL DEFAULT 'snapshot/1',
    "content_hash" VARCHAR(64),
    "sealed_at" TIMESTAMPTZ(3),

    CONSTRAINT "decision_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "snapshot_members" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "snapshot_id" UUID NOT NULL,
    "record_version_id" UUID NOT NULL,
    "supplier_owner_id" UUID,
    "department_owner_id" UUID,
    "purchase_line_owner_id" UUID,
    "role" TEXT NOT NULL,

    CONSTRAINT "snapshot_members_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_events" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "actor_user_id" UUID NOT NULL,
    "actor_kind" TEXT NOT NULL DEFAULT 'user',
    "operation" TEXT NOT NULL,
    "before_version_id" UUID,
    "after_version_id" UUID,
    "source_identity_id" UUID,
    "source_reference_id" UUID,
    "snapshot_id" UUID,
    "recorded_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "correlation_id" UUID,
    "context" JSONB,

    CONSTRAINT "audit_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "currencies_code_key" ON "currencies"("code");

-- CreateIndex
CREATE INDEX "departments_head_idx" ON "departments"("current_version_id");

-- CreateIndex
CREATE INDEX "users_department_idx" ON "users"("department_id");

-- CreateIndex
CREATE UNIQUE INDEX "users_auth_identity_key" ON "users"("auth_issuer", "auth_subject");

-- CreateIndex
CREATE INDEX "suppliers_head_idx" ON "suppliers"("current_version_id");

-- CreateIndex
CREATE INDEX "purchase_order_lines_head_idx" ON "purchase_order_lines"("current_version_id");

-- CreateIndex
CREATE INDEX "purchase_order_lines_supplier_idx" ON "purchase_order_lines"("supplier_id");

-- CreateIndex
CREATE INDEX "purchase_order_lines_department_idx" ON "purchase_order_lines"("department_id");

-- CreateIndex
CREATE INDEX "purchase_order_lines_currency_idx" ON "purchase_order_lines"("currency_id");

-- CreateIndex
CREATE INDEX "source_identities_supplier_idx" ON "source_identities"("supplier_id");

-- CreateIndex
CREATE INDEX "source_identities_department_idx" ON "source_identities"("department_id");

-- CreateIndex
CREATE INDEX "source_identities_line_idx" ON "source_identities"("purchase_order_line_id");

-- CreateIndex
CREATE UNIQUE INDEX "source_identities_canonical_key" ON "source_identities"("source_namespace", "source_entity_kind", "source_id");

-- CreateIndex
CREATE UNIQUE INDEX "source_identities_scope_key" ON "source_identities"("id", "source_namespace", "source_entity_kind");

-- CreateIndex
CREATE INDEX "source_references_identity_time_idx" ON "source_references"("source_identity_id", "recorded_at");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_predecessor_key" ON "record_versions"("supersedes_version_id");

-- CreateIndex
CREATE INDEX "record_versions_source_idx" ON "record_versions"("source_reference_id");

-- CreateIndex
CREATE INDEX "record_versions_actor_idx" ON "record_versions"("actor_user_id");

-- CreateIndex
CREATE INDEX "record_versions_supplier_context_idx" ON "record_versions"("supplier_id");

-- CreateIndex
CREATE INDEX "record_versions_department_context_idx" ON "record_versions"("department_id");

-- CreateIndex
CREATE INDEX "record_versions_currency_context_idx" ON "record_versions"("currency_id");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_supplier_pair" ON "record_versions"("id", "supplier_owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_department_pair" ON "record_versions"("id", "department_owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_line_pair" ON "record_versions"("id", "purchase_line_owner_id");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_supplier_revision" ON "record_versions"("supplier_owner_id", "revision_no");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_department_revision" ON "record_versions"("department_owner_id", "revision_no");

-- CreateIndex
CREATE UNIQUE INDEX "record_versions_line_revision" ON "record_versions"("purchase_line_owner_id", "revision_no");

-- CreateIndex
CREATE INDEX "decision_snapshots_actor_idx" ON "decision_snapshots"("actor_user_id");

-- CreateIndex
CREATE INDEX "decision_snapshots_root_idx" ON "decision_snapshots"("root_record_version_id");

-- CreateIndex
CREATE INDEX "snapshot_members_version_idx" ON "snapshot_members"("record_version_id");

-- CreateIndex
CREATE UNIQUE INDEX "snapshot_members_version_key" ON "snapshot_members"("snapshot_id", "record_version_id");

-- CreateIndex
CREATE UNIQUE INDEX "snapshot_members_role_key" ON "snapshot_members"("snapshot_id", "role");

-- CreateIndex
CREATE UNIQUE INDEX "audit_events_after_version_key" ON "audit_events"("after_version_id");

-- CreateIndex
CREATE INDEX "audit_events_actor_time_idx" ON "audit_events"("actor_user_id", "recorded_at");

-- CreateIndex
CREATE INDEX "audit_events_before_idx" ON "audit_events"("before_version_id");

-- CreateIndex
CREATE INDEX "audit_events_identity_idx" ON "audit_events"("source_identity_id");

-- CreateIndex
CREATE INDEX "audit_events_source_idx" ON "audit_events"("source_reference_id");

-- CreateIndex
CREATE INDEX "audit_events_snapshot_idx" ON "audit_events"("snapshot_id");

-- AddForeignKey
ALTER TABLE "departments" ADD CONSTRAINT "departments_head_fk" FOREIGN KEY ("current_version_id", "id") REFERENCES "record_versions"("id", "department_owner_id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "users" ADD CONSTRAINT "users_department_id_fkey" FOREIGN KEY ("department_id") REFERENCES "departments"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "suppliers" ADD CONSTRAINT "suppliers_head_fk" FOREIGN KEY ("current_version_id", "id") REFERENCES "record_versions"("id", "supplier_owner_id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "purchase_order_lines" ADD CONSTRAINT "purchase_order_lines_supplier_id_fkey" FOREIGN KEY ("supplier_id") REFERENCES "suppliers"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "purchase_order_lines" ADD CONSTRAINT "purchase_order_lines_department_id_fkey" FOREIGN KEY ("department_id") REFERENCES "departments"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "purchase_order_lines" ADD CONSTRAINT "purchase_order_lines_currency_id_fkey" FOREIGN KEY ("currency_id") REFERENCES "currencies"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "purchase_order_lines" ADD CONSTRAINT "purchase_order_lines_head_fk" FOREIGN KEY ("current_version_id", "id") REFERENCES "record_versions"("id", "purchase_line_owner_id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "source_identities" ADD CONSTRAINT "source_identities_supplier_id_fkey" FOREIGN KEY ("supplier_id") REFERENCES "suppliers"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "source_identities" ADD CONSTRAINT "source_identities_department_id_fkey" FOREIGN KEY ("department_id") REFERENCES "departments"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "source_identities" ADD CONSTRAINT "source_identities_purchase_order_line_id_fkey" FOREIGN KEY ("purchase_order_line_id") REFERENCES "purchase_order_lines"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "source_references" ADD CONSTRAINT "source_references_scope_fk" FOREIGN KEY ("source_identity_id", "source_namespace", "source_entity_kind") REFERENCES "source_identities"("id", "source_namespace", "source_entity_kind") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_supplier_owner_id_fkey" FOREIGN KEY ("supplier_owner_id") REFERENCES "suppliers"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_department_owner_id_fkey" FOREIGN KEY ("department_owner_id") REFERENCES "departments"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_purchase_line_owner_id_fkey" FOREIGN KEY ("purchase_line_owner_id") REFERENCES "purchase_order_lines"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_supersedes_version_id_fkey" FOREIGN KEY ("supersedes_version_id") REFERENCES "record_versions"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_source_reference_id_fkey" FOREIGN KEY ("source_reference_id") REFERENCES "source_references"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_supplier_id_fkey" FOREIGN KEY ("supplier_id") REFERENCES "suppliers"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_department_id_fkey" FOREIGN KEY ("department_id") REFERENCES "departments"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "record_versions" ADD CONSTRAINT "record_versions_currency_id_fkey" FOREIGN KEY ("currency_id") REFERENCES "currencies"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "decision_snapshots" ADD CONSTRAINT "decision_snapshots_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "decision_snapshots" ADD CONSTRAINT "decision_snapshots_root_fk" FOREIGN KEY ("id", "root_record_version_id") REFERENCES "snapshot_members"("snapshot_id", "record_version_id") ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "snapshot_members" ADD CONSTRAINT "snapshot_members_snapshot_id_fkey" FOREIGN KEY ("snapshot_id") REFERENCES "decision_snapshots"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "snapshot_members" ADD CONSTRAINT "snapshot_members_supplier_fk" FOREIGN KEY ("record_version_id", "supplier_owner_id") REFERENCES "record_versions"("id", "supplier_owner_id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "snapshot_members" ADD CONSTRAINT "snapshot_members_department_fk" FOREIGN KEY ("record_version_id", "department_owner_id") REFERENCES "record_versions"("id", "department_owner_id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "snapshot_members" ADD CONSTRAINT "snapshot_members_line_fk" FOREIGN KEY ("record_version_id", "purchase_line_owner_id") REFERENCES "record_versions"("id", "purchase_line_owner_id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_before_version_id_fkey" FOREIGN KEY ("before_version_id") REFERENCES "record_versions"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_after_version_id_fkey" FOREIGN KEY ("after_version_id") REFERENCES "record_versions"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_source_identity_id_fkey" FOREIGN KEY ("source_identity_id") REFERENCES "source_identities"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_source_reference_id_fkey" FOREIGN KEY ("source_reference_id") REFERENCES "source_references"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_snapshot_id_fkey" FOREIGN KEY ("snapshot_id") REFERENCES "decision_snapshots"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;


-- CUSTOM_INVARIANTS

-- This complete migration is applied once. No data import, seed, role creation
-- or connection is embedded here. Runtime grants are a separate, explicit step.
ALTER TABLE app.departments ALTER CONSTRAINT departments_head_fk DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE app.suppliers ALTER CONSTRAINT suppliers_head_fk DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE app.purchase_order_lines ALTER CONSTRAINT purchase_order_lines_head_fk DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE app.decision_snapshots ALTER CONSTRAINT decision_snapshots_root_fk DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.currencies ADD CONSTRAINT currencies_code_check
  CHECK (code ~ '^[A-Z]{3}$' AND btrim(name) <> '');
ALTER TABLE app.users ADD CONSTRAINT users_identity_check
  CHECK (btrim(display_name) <> '' AND ((auth_issuer IS NULL) = (auth_subject IS NULL))
    AND (auth_issuer IS NULL OR (btrim(auth_issuer) <> '' AND btrim(auth_subject) <> '')));
ALTER TABLE app.suppliers ADD CONSTRAINT suppliers_fields_check
  CHECK (btrim(name) <> '' AND (country_code IS NULL OR country_code ~ '^[A-Z]{2}$'));
ALTER TABLE app.departments ADD CONSTRAINT departments_fields_check CHECK (btrim(name) <> '');
ALTER TABLE app.purchase_order_lines ADD CONSTRAINT purchase_order_lines_money_check
  CHECK (((amount IS NULL AND unit_price IS NULL) OR currency_id IS NOT NULL)
    AND (amount IS NULL OR amount::text NOT IN ('NaN','Infinity','-Infinity'))
    AND (unit_price IS NULL OR unit_price::text NOT IN ('NaN','Infinity','-Infinity'))
    AND (quantity IS NULL OR quantity::text NOT IN ('NaN','Infinity','-Infinity')));

ALTER TABLE app.source_identities ADD CONSTRAINT source_identities_owner_check CHECK (
  btrim(source_namespace) <> '' AND btrim(source_id) <> ''
  AND source_entity_kind IN ('supplier','department','purchase_order_line')
  AND ((num_nonnulls(supplier_id,department_id,purchase_order_line_id)=0 AND resolved_at IS NULL)
    OR (num_nonnulls(supplier_id,department_id,purchase_order_line_id)=1 AND resolved_at IS NOT NULL
      AND ((supplier_id IS NOT NULL AND source_entity_kind='supplier')
        OR (department_id IS NOT NULL AND source_entity_kind='department')
        OR (purchase_order_line_id IS NOT NULL AND source_entity_kind='purchase_order_line')))));
ALTER TABLE app.source_references ADD CONSTRAINT source_references_fields_check CHECK (
  btrim(source_namespace) <> '' AND btrim(source_entity_kind) <> ''
  AND (content_hash IS NULL OR content_hash ~ '^[a-f0-9]{64}$')
  AND availability_status='unverified' AND (available_at IS NULL OR isfinite(available_at)));

ALTER TABLE app.record_versions ADD CONSTRAINT record_versions_owner_check
  CHECK (num_nonnulls(supplier_owner_id,department_owner_id,purchase_line_owner_id)=1);
ALTER TABLE app.record_versions ADD CONSTRAINT record_versions_chain_check
  CHECK (revision_no>0 AND ((revision_no=1) = (supersedes_version_id IS NULL)));
ALTER TABLE app.record_versions ADD CONSTRAINT record_versions_state_check CHECK (
  payload_schema=1 AND jsonb_typeof(payload)='object'
  AND (purchase_line_owner_id IS NOT NULL OR num_nonnulls(supplier_id,department_id,currency_id)=0)
  AND (effective_from IS NULL OR isfinite(effective_from))
  AND (effective_to IS NULL OR (effective_from IS NOT NULL AND isfinite(effective_to) AND effective_to>effective_from)));

ALTER TABLE app.snapshot_members ADD CONSTRAINT snapshot_members_owner_check CHECK (
  num_nonnulls(supplier_owner_id,department_owner_id,purchase_line_owner_id)=1
  AND ((role='root' AND purchase_line_owner_id IS NOT NULL)
    OR (role='supplier_context' AND supplier_owner_id IS NOT NULL)
    OR (role='department_context' AND department_owner_id IS NOT NULL)));
CREATE UNIQUE INDEX snapshot_members_supplier_once ON app.snapshot_members(snapshot_id,supplier_owner_id)
  WHERE supplier_owner_id IS NOT NULL;
CREATE UNIQUE INDEX snapshot_members_department_once ON app.snapshot_members(snapshot_id,department_owner_id)
  WHERE department_owner_id IS NOT NULL;
CREATE UNIQUE INDEX snapshot_members_line_once ON app.snapshot_members(snapshot_id,purchase_line_owner_id)
  WHERE purchase_line_owner_id IS NOT NULL;
ALTER TABLE app.decision_snapshots ADD CONSTRAINT decision_snapshots_state_check CHECK (
  purpose='record_capture' AND capture_mode='contemporaneous' AND availability_status='captured_now'
  AND hash_format='snapshot/1' AND isfinite(captured_at) AND knowledge_cutoff_at=captured_at
  AND ((status='draft' AND sealed_at IS NULL AND content_hash IS NULL)
    OR (status='sealed' AND sealed_at IS NOT NULL AND sealed_at>=captured_at AND isfinite(sealed_at)
      AND content_hash IS NOT NULL AND content_hash ~ '^[a-f0-9]{64}$')));
ALTER TABLE app.audit_events ADD CONSTRAINT audit_events_subject_check CHECK (
  actor_kind='user'
  AND num_nonnulls(after_version_id,source_identity_id,source_reference_id,snapshot_id)=1
  AND (before_version_id IS NULL OR after_version_id IS NOT NULL)
  AND operation IN ('create','revise','identity_register','identity_resolve','source_observe','capture','seal'));

CREATE FUNCTION app.deny_mutation() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
BEGIN
  RAISE EXCEPTION 'Immutable evidence: % %', TG_TABLE_NAME, TG_OP USING ERRCODE='55000';
END $$;

-- All callable parsers see the original text before a typmod can round it.
CREATE FUNCTION app.exact_decimal(value text, precision_digits integer, scale_digits integer)
RETURNS numeric LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,app AS $$
DECLARE result numeric;
BEGIN
  IF value IS NULL THEN RETURN NULL; END IF;
  IF length(value)>precision_digits+2 OR value !~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$'
     OR length(split_part(value,'.',2))>scale_digits THEN
    RAISE EXCEPTION 'Decimal representation/precision invalid' USING ERRCODE='22023';
  END IF;
  result := value::numeric;
  IF abs(result)>=('1'||repeat('0',precision_digits-scale_digits))::numeric THEN
    RAISE EXCEPTION 'Decimal outside precision' USING ERRCODE='22023';
  END IF;
  RETURN result;
END $$;

CREATE FUNCTION app.exact_instant(value text) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,app AS $$
BEGIN
  IF value IS NULL THEN RETURN NULL; END IF;
  IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,3})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$' THEN
    RAISE EXCEPTION 'Use an explicit offset and at most milliseconds' USING ERRCODE='22023';
  END IF;
  RETURN value::timestamptz;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
  RAISE EXCEPTION 'Invalid instant' USING ERRCODE='22023';
END $$;

CREATE FUNCTION app.exact_date(value text) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,app AS $$
BEGIN
  IF value IS NULL THEN RETURN NULL; END IF;
  IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
    RAISE EXCEPTION 'Civil date must be YYYY-MM-DD' USING ERRCODE='22023';
  END IF;
  RETURN value::date;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
  RAISE EXCEPTION 'Invalid civil date' USING ERRCODE='22023';
END $$;

-- Exhaustive scalar mapping. FKs are separate typed version columns, never JSON relationships.
-- Supplier: name,country_code,status,tier. Department: name,code.
-- Line: description,po_date,quantity,unit_price,amount (+ supplier/department/currency FKs).
-- id/current_version_id/created_at/updated_at are technical, not duplicated business state.
CREATE FUNCTION app.normalize_payload(kind text, state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,app AS $$
DECLARE keys text[]; item record; result jsonb;
BEGIN
  IF state IS NULL OR jsonb_typeof(state)<>'object' THEN
    RAISE EXCEPTION 'State must be an object' USING ERRCODE='22023';
  END IF;
  CASE kind
    WHEN 'supplier' THEN keys:=ARRAY['name','country_code','status','tier'];
    WHEN 'department' THEN keys:=ARRAY['name','code'];
    WHEN 'purchase_order_line' THEN keys:=ARRAY['description','po_date','quantity','unit_price','amount'];
    ELSE RAISE EXCEPTION 'Unsupported owner kind' USING ERRCODE='22023';
  END CASE;
  FOR item IN SELECT key,value FROM jsonb_each(state) LOOP
    IF NOT item.key=ANY(keys) OR jsonb_typeof(item.value) NOT IN ('string','null') THEN
      RAISE EXCEPTION 'Unknown state key or non-text value: %',item.key USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF kind IN ('supplier','department') AND coalesce(btrim(state->>'name'),'')='' THEN
    RAISE EXCEPTION 'Name required' USING ERRCODE='22023';
  END IF;
  IF kind='supplier' THEN
    IF state->>'country_code' IS NOT NULL AND state->>'country_code' !~ '^[A-Z]{2}$' THEN
      RAISE EXCEPTION 'Country code must have two uppercase letters' USING ERRCODE='22023';
    END IF;
    result:=jsonb_build_object('name',state->>'name','country_code',state->>'country_code',
      'status',state->>'status','tier',state->>'tier');
  ELSIF kind='department' THEN
    result:=jsonb_build_object('name',state->>'name','code',state->>'code');
  ELSE
    result:=jsonb_build_object('description',state->>'description',
      'po_date',to_char(app.exact_date(state->>'po_date'),'YYYY-MM-DD'),
      'quantity',(app.exact_decimal(state->>'quantity',20,6)::numeric(20,6))::text,
      'unit_price',(app.exact_decimal(state->>'unit_price',24,8)::numeric(24,8))::text,
      'amount',(app.exact_decimal(state->>'amount',24,6)::numeric(24,6))::text);
  END IF;
  RETURN result;
END $$;

CREATE FUNCTION app.require_actor(actor uuid) RETURNS void LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
BEGIN
  PERFORM 1 FROM app.users WHERE id=actor AND is_active FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Active actor required' USING ERRCODE='23503'; END IF;
END $$;

CREATE FUNCTION app.check_version_insert() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
DECLARE previous app.record_versions; kind text; head uuid; origin app.source_identities;
BEGIN
  IF num_nonnulls(NEW.supplier_owner_id,NEW.department_owner_id,NEW.purchase_line_owner_id)<>1 THEN
    RAISE EXCEPTION 'Exactly one typed owner required' USING ERRCODE='23514';
  END IF;
  IF NEW.supplier_owner_id IS NOT NULL THEN
    kind:='supplier';
    SELECT current_version_id INTO head FROM app.suppliers WHERE id=NEW.supplier_owner_id FOR UPDATE;
  ELSIF NEW.department_owner_id IS NOT NULL THEN
    kind:='department';
    SELECT current_version_id INTO head FROM app.departments WHERE id=NEW.department_owner_id FOR UPDATE;
  ELSE
    kind:='purchase_order_line';
    SELECT current_version_id INTO head FROM app.purchase_order_lines WHERE id=NEW.purchase_line_owner_id FOR UPDATE;
  END IF;
  IF head IS NULL THEN RAISE EXCEPTION 'Owner absent' USING ERRCODE='23503'; END IF;
  IF NEW.revision_no=1 THEN
    IF NEW.supersedes_version_id IS NOT NULL OR head<>NEW.id THEN
      RAISE EXCEPTION 'Initial revision must be the first head' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT * INTO previous FROM app.record_versions WHERE id=NEW.supersedes_version_id;
    IF NOT FOUND OR NEW.revision_no<>previous.revision_no+1
       OR NEW.supplier_owner_id IS DISTINCT FROM previous.supplier_owner_id
       OR NEW.department_owner_id IS DISTINCT FROM previous.department_owner_id
       OR NEW.purchase_line_owner_id IS DISTINCT FROM previous.purchase_line_owner_id
       OR NEW.supersedes_version_id IS DISTINCT FROM head THEN
      RAISE EXCEPTION 'Invalid predecessor/revision/head' USING ERRCODE='23514';
    END IF;
  END IF;
  NEW.payload:=app.normalize_payload(kind,NEW.payload);
  IF NEW.source_reference_id IS NOT NULL THEN
    SELECT i.* INTO origin FROM app.source_references r JOIN app.source_identities i ON i.id=r.source_identity_id
      WHERE r.id=NEW.source_reference_id;
    IF FOUND AND (origin.resolved_at IS NULL
       OR origin.supplier_id IS DISTINCT FROM NEW.supplier_owner_id
       OR origin.department_id IS DISTINCT FROM NEW.department_owner_id
       OR origin.purchase_order_line_id IS DISTINCT FROM NEW.purchase_line_owner_id) THEN
      RAISE EXCEPTION 'Source identity belongs to another/unresolved owner' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER record_versions_insert BEFORE INSERT ON app.record_versions
  FOR EACH ROW EXECUTE FUNCTION app.check_version_insert();

CREATE FUNCTION app.validate_projection(kind text, owner uuid) RETURNS void LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
DECLARE version app.record_versions; projected jsonb; head uuid; s uuid; d uuid; c uuid;
BEGIN
  IF kind='supplier' THEN
    SELECT current_version_id,jsonb_build_object('name',name,'country_code',country_code,'status',status,'tier',tier)
      INTO head,projected FROM app.suppliers WHERE id=owner;
  ELSIF kind='department' THEN
    SELECT current_version_id,jsonb_build_object('name',name,'code',code)
      INTO head,projected FROM app.departments WHERE id=owner;
  ELSE
    SELECT current_version_id,jsonb_build_object('description',description,
      'po_date',to_char(po_date,'YYYY-MM-DD'),'quantity',quantity::text,'unit_price',unit_price::text,'amount',amount::text),
      supplier_id,department_id,currency_id INTO head,projected,s,d,c FROM app.purchase_order_lines WHERE id=owner;
  END IF;
  SELECT * INTO version FROM app.record_versions WHERE id=head;
  IF NOT FOUND OR NOT (
    (kind='supplier' AND version.supplier_owner_id IS NOT DISTINCT FROM owner) OR
    (kind='department' AND version.department_owner_id IS NOT DISTINCT FROM owner) OR
    (kind='purchase_order_line' AND version.purchase_line_owner_id IS NOT DISTINCT FROM owner)) THEN
    RAISE EXCEPTION 'Head missing or belongs to another owner' USING ERRCODE='23503';
  END IF;
  IF projected IS DISTINCT FROM version.payload OR s IS DISTINCT FROM version.supplier_id
     OR d IS DISTINCT FROM version.department_id OR c IS DISTINCT FROM version.currency_id
     OR EXISTS(SELECT 1 FROM app.record_versions WHERE supersedes_version_id=head) THEN
    RAISE EXCEPTION 'Projection/head differs from terminal version' USING ERRCODE='23514';
  END IF;
END $$;

CREATE FUNCTION app.check_projection_deferred() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
BEGIN
  PERFORM app.validate_projection(TG_ARGV[0],NEW.id);
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER suppliers_projection AFTER INSERT OR UPDATE ON app.suppliers
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_projection_deferred('supplier');
CREATE CONSTRAINT TRIGGER departments_projection AFTER INSERT OR UPDATE ON app.departments
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_projection_deferred('department');
CREATE CONSTRAINT TRIGGER purchase_order_lines_projection AFTER INSERT OR UPDATE ON app.purchase_order_lines
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_projection_deferred('purchase_order_line');

CREATE FUNCTION app.check_version_deferred() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
DECLARE event app.audit_events;
BEGIN
  PERFORM app.validate_projection(
    CASE WHEN NEW.supplier_owner_id IS NOT NULL THEN 'supplier'
         WHEN NEW.department_owner_id IS NOT NULL THEN 'department' ELSE 'purchase_order_line' END,
    coalesce(NEW.supplier_owner_id,NEW.department_owner_id,NEW.purchase_line_owner_id));
  SELECT * INTO event FROM app.audit_events WHERE after_version_id=NEW.id;
  IF NOT FOUND OR event.before_version_id IS DISTINCT FROM NEW.supersedes_version_id
     OR event.actor_user_id<>NEW.actor_user_id
     OR event.operation <> (
    CASE
        WHEN NEW.revision_no = 1 THEN 'create'
        ELSE 'revise'
    END
) THEN
    RAISE EXCEPTION 'Exactly one consistent audit event required' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER record_versions_consistency AFTER INSERT ON app.record_versions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_version_deferred();

-- Private common implementation; runtime gets only the three typed wrappers.
CREATE FUNCTION app.internal_write_record(
  kind text, entity uuid, expected uuid, state jsonb, supplier uuid, department uuid, currency uuid,
  actor uuid, source uuid, valid_from text, valid_to text)
RETURNS TABLE(entity_id uuid,version_id uuid,revision_no integer)
LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
DECLARE payload jsonb; old_head uuid; revision integer:=1; owner uuid:=coalesce(entity,gen_random_uuid());
  next_version uuid:=gen_random_uuid(); instant timestamptz(3):=clock_timestamp();
  from_at timestamptz; to_at timestamptz;
BEGIN
  PERFORM app.require_actor(actor);
  payload:=app.normalize_payload(kind,state);
  from_at:=app.exact_instant(valid_from); to_at:=app.exact_instant(valid_to);
  IF entity IS NULL THEN
    IF expected IS NOT NULL THEN RAISE EXCEPTION 'Create cannot have a predecessor' USING ERRCODE='22023'; END IF;
    CASE kind
      WHEN 'supplier' THEN INSERT INTO app.suppliers(id,name,country_code,status,tier,current_version_id,created_at,updated_at)
        VALUES(owner,payload->>'name',payload->>'country_code',payload->>'status',payload->>'tier',next_version,instant,instant);
      WHEN 'department' THEN INSERT INTO app.departments(id,name,code,current_version_id,created_at,updated_at)
        VALUES(owner,payload->>'name',payload->>'code',next_version,instant,instant);
      ELSE INSERT INTO app.purchase_order_lines(id,description,po_date,supplier_id,department_id,currency_id,
        quantity,unit_price,amount,current_version_id,created_at,updated_at)
        VALUES(owner,payload->>'description',(payload->>'po_date')::date,supplier,department,currency,
          (payload->>'quantity')::numeric,(payload->>'unit_price')::numeric,(payload->>'amount')::numeric,next_version,instant,instant);
    END CASE;
  ELSE
    CASE kind
      WHEN 'supplier' THEN SELECT current_version_id INTO old_head FROM app.suppliers WHERE id=owner FOR UPDATE;
      WHEN 'department' THEN SELECT current_version_id INTO old_head FROM app.departments WHERE id=owner FOR UPDATE;
      ELSE SELECT current_version_id INTO old_head FROM app.purchase_order_lines WHERE id=owner FOR UPDATE;
    END CASE;
    IF old_head IS NULL THEN RAISE EXCEPTION 'Entity absent' USING ERRCODE='23503'; END IF;
    IF expected IS NULL OR old_head<>expected THEN
      RAISE EXCEPTION 'Stale expected head; explicit retry requires rereading' USING ERRCODE='40001';
    END IF;
    SELECT v.revision_no+1 INTO revision FROM app.record_versions v WHERE v.id=old_head;
  END IF;
  INSERT INTO app.record_versions(id,supplier_owner_id,department_owner_id,purchase_line_owner_id,
    revision_no,supersedes_version_id,source_reference_id,actor_user_id,recorded_at,effective_from,effective_to,
    payload,supplier_id,department_id,currency_id)
    VALUES(next_version,CASE WHEN kind='supplier' THEN owner END,CASE WHEN kind='department' THEN owner END,
      CASE WHEN kind='purchase_order_line' THEN owner END,revision,old_head,source,actor,instant,from_at,to_at,
      payload,supplier,department,currency);
  IF entity IS NOT NULL THEN
    CASE kind
      WHEN 'supplier' THEN UPDATE app.suppliers SET name=payload->>'name',country_code=payload->>'country_code',
        status=payload->>'status',tier=payload->>'tier',current_version_id=next_version,updated_at=instant WHERE id=owner;
      WHEN 'department' THEN UPDATE app.departments SET name=payload->>'name',code=payload->>'code',
        current_version_id=next_version,updated_at=instant WHERE id=owner;
      ELSE UPDATE app.purchase_order_lines SET description=payload->>'description',po_date=(payload->>'po_date')::date,
        quantity=(payload->>'quantity')::numeric,unit_price=(payload->>'unit_price')::numeric,amount=(payload->>'amount')::numeric,
        supplier_id=supplier,department_id=department,currency_id=currency,current_version_id=next_version,updated_at=instant WHERE id=owner;
    END CASE;
  END IF;
  INSERT INTO app.audit_events(actor_user_id,operation,before_version_id,after_version_id,recorded_at,context)
    VALUES(actor,CASE WHEN revision=1 THEN 'create' ELSE 'revise' END,old_head,next_version,instant,
      jsonb_build_object('database_session',session_user));
  RETURN QUERY SELECT owner,next_version,revision;
END $$;

CREATE FUNCTION app.write_supplier(entity uuid,expected uuid,state jsonb,actor uuid,
  source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL)
RETURNS TABLE(entity_id uuid,version_id uuid,revision_no integer) LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
  SELECT * FROM app.internal_write_record('supplier',entity,expected,state,NULL,NULL,NULL,actor,source,valid_from,valid_to)
$$;
CREATE FUNCTION app.write_department(entity uuid,expected uuid,state jsonb,actor uuid,
  source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL)
RETURNS TABLE(entity_id uuid,version_id uuid,revision_no integer) LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
  SELECT * FROM app.internal_write_record('department',entity,expected,state,NULL,NULL,NULL,actor,source,valid_from,valid_to)
$$;
CREATE FUNCTION app.write_purchase_order_line(entity uuid,expected uuid,state jsonb,
  supplier uuid,department uuid,currency uuid,actor uuid,
  source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL)
RETURNS TABLE(entity_id uuid,version_id uuid,revision_no integer) LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
  SELECT * FROM app.internal_write_record('purchase_order_line',entity,expected,state,supplier,department,currency,
    actor,source,valid_from,valid_to)
$$;

CREATE FUNCTION app.guard_source_identity() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
BEGIN
  IF OLD.resolved_at IS NOT NULL OR
     (to_jsonb(NEW)-ARRAY['supplier_id','department_id','purchase_order_line_id','resolved_at'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['supplier_id','department_id','purchase_order_line_id','resolved_at']) THEN
    RAISE EXCEPTION 'Canonical identity cannot be rewritten/remapped' USING ERRCODE='55000';
  END IF;
  IF NEW.resolved_at IS NULL THEN RAISE EXCEPTION 'Update must resolve the identity' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER source_identities_update BEFORE UPDATE ON app.source_identities
  FOR EACH ROW EXECUTE FUNCTION app.guard_source_identity();

CREATE FUNCTION app.register_source_identity(namespace text,kind text,external_id text,actor uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE result uuid;
BEGIN
  PERFORM app.require_actor(actor);
  INSERT INTO app.source_identities(source_namespace,source_entity_kind,source_id)
    VALUES(namespace,kind,external_id) RETURNING id INTO result;
  INSERT INTO app.audit_events(actor_user_id,operation,source_identity_id,context)
    VALUES(actor,'identity_register',result,jsonb_build_object('database_session',session_user));
  RETURN result;
END $$;

CREATE FUNCTION app.resolve_source_identity(identity_id uuid,supplier uuid,department uuid,line uuid,actor uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
  PERFORM app.require_actor(actor);
  UPDATE app.source_identities SET supplier_id=supplier,department_id=department,
    purchase_order_line_id=line,resolved_at=clock_timestamp() WHERE id=identity_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Identity absent' USING ERRCODE='23503'; END IF;
  INSERT INTO app.audit_events(actor_user_id,operation,source_identity_id,context)
    VALUES(actor,'identity_resolve',identity_id,jsonb_build_object('database_session',session_user));
END $$;

CREATE FUNCTION app.observe_source(namespace text,kind text,actor uuid,identity_id uuid DEFAULT NULL,
  source_version text DEFAULT NULL,record_key text DEFAULT NULL,locator text DEFAULT NULL,
  content_hash text DEFAULT NULL,original_content jsonb DEFAULT NULL,available_at text DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE result uuid;
BEGIN
  PERFORM app.require_actor(actor);
  IF content_hash IS NOT NULL AND content_hash !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'Expected lowercase SHA-256 hex' USING ERRCODE='22023';
  END IF;
  INSERT INTO app.source_references(source_identity_id,source_namespace,source_entity_kind,source_version,
    source_record_key,locator,content_hash,original_content,available_at)
    VALUES(identity_id,namespace,kind,source_version,record_key,locator,content_hash,original_content,app.exact_instant(available_at))
    RETURNING id INTO result;
  INSERT INTO app.audit_events(actor_user_id,operation,source_reference_id,context)
    VALUES(actor,'source_observe',result,jsonb_build_object('database_session',session_user));
  RETURN result;
END $$;

CREATE FUNCTION app.require_read_committed() RETURNS void LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
BEGIN
  IF current_setting('transaction_isolation')<>'read committed' THEN
    RAISE EXCEPTION 'Snapshot operations require READ COMMITTED' USING ERRCODE='25001';
  END IF;
END $$;

CREATE FUNCTION app.guard_snapshot() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
DECLARE root app.record_versions;
BEGIN
  PERFORM app.require_read_committed();
  IF TG_OP='UPDATE' AND OLD.status='sealed' THEN
    RAISE EXCEPTION 'Snapshot sealed' USING ERRCODE='55000';
  END IF;
  IF TG_OP='UPDATE' AND
    (to_jsonb(NEW)-ARRAY['root_record_version_id','status','sealed_at','content_hash'])
      IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['root_record_version_id','status','sealed_at','content_hash']) THEN
    RAISE EXCEPTION 'Capture metadata immutable' USING ERRCODE='55000';
  END IF;
  SELECT * INTO root FROM app.record_versions WHERE id=NEW.root_record_version_id;
  IF NOT FOUND OR root.purchase_line_owner_id IS NULL THEN
    RAISE EXCEPTION 'Snapshot root must be a purchase line version' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' AND NEW.status<>'draft' THEN
    RAISE EXCEPTION 'Create a draft before sealing' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER decision_snapshots_guard BEFORE INSERT OR UPDATE ON app.decision_snapshots
  FOR EACH ROW EXECUTE FUNCTION app.guard_snapshot();

CREATE FUNCTION app.guard_snapshot_member() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
DECLARE parent uuid; state text;
BEGIN
  PERFORM app.require_read_committed();
  parent:=CASE WHEN TG_OP='DELETE' THEN OLD.snapshot_id ELSE NEW.snapshot_id END;
  IF TG_OP='UPDATE' AND NEW.snapshot_id<>OLD.snapshot_id THEN
    RAISE EXCEPTION 'Cannot move a member to another snapshot' USING ERRCODE='55000';
  END IF;
  SELECT status INTO state FROM app.decision_snapshots WHERE id=parent FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Snapshot absent' USING ERRCODE='23503'; END IF;
  IF state='sealed' THEN RAISE EXCEPTION 'Snapshot members sealed' USING ERRCODE='55000'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER snapshot_members_guard BEFORE INSERT OR UPDATE OR DELETE ON app.snapshot_members
  FOR EACH ROW EXECUTE FUNCTION app.guard_snapshot_member();

CREATE FUNCTION app.validate_snapshot_members(snapshot uuid) RETURNS void LANGUAGE plpgsql
SET search_path=pg_catalog,app AS $$
DECLARE capture app.decision_snapshots; root app.record_versions; total integer;
BEGIN
  SELECT * INTO capture FROM app.decision_snapshots WHERE id=snapshot;
  SELECT * INTO root FROM app.record_versions WHERE id=capture.root_record_version_id;
  SELECT count(*) INTO total FROM app.snapshot_members WHERE snapshot_id=snapshot;
  IF root.purchase_line_owner_id IS NULL OR
    NOT EXISTS(SELECT 1 FROM app.snapshot_members WHERE snapshot_id=snapshot AND role='root'
      AND record_version_id=root.id AND purchase_line_owner_id=root.purchase_line_owner_id) OR
    total<>1+(root.supplier_id IS NOT NULL)::integer+(root.department_id IS NOT NULL)::integer OR
    (root.supplier_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM app.snapshot_members WHERE snapshot_id=snapshot AND role='supplier_context' AND supplier_owner_id=root.supplier_id)) OR
    (root.department_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM app.snapshot_members WHERE snapshot_id=snapshot AND role='department_context' AND department_owner_id=root.department_id)) OR
    EXISTS(SELECT 1 FROM app.snapshot_members m JOIN app.record_versions v ON v.id=m.record_version_id
      WHERE m.snapshot_id=snapshot AND v.recorded_at>capture.knowledge_cutoff_at) THEN
    RAISE EXCEPTION 'Incomplete, conflicting or temporally invalid capture' USING ERRCODE='23514';
  END IF;
END $$;

CREATE FUNCTION app.snapshot_digest(snapshot uuid) RETURNS text LANGUAGE sql STABLE
SET search_path=pg_catalog,app SET timezone='UTC' SET datestyle='ISO, YMD' AS $$
  SELECT encode(sha256(convert_to(jsonb_build_object(
    'format',s.hash_format,'id',s.id,'purpose',s.purpose,'root',s.root_record_version_id,
    'actor',s.actor_user_id,'cutoff',s.knowledge_cutoff_at,'captured_at',s.captured_at,
    'capture_mode',s.capture_mode,'availability_status',s.availability_status,
    'members',(SELECT jsonb_agg(jsonb_build_object('role',m.role,'version',to_jsonb(v))
      ORDER BY m.role,m.record_version_id)
      FROM app.snapshot_members m JOIN app.record_versions v ON v.id=m.record_version_id WHERE m.snapshot_id=s.id)
    )::text,'UTF8')),'hex') FROM app.decision_snapshots s WHERE s.id=snapshot
$$;

CREATE FUNCTION app.check_sealed_snapshot() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
BEGIN
  IF NEW.status='sealed' THEN
    PERFORM app.validate_snapshot_members(NEW.id);
    IF NEW.content_hash IS DISTINCT FROM app.snapshot_digest(NEW.id) THEN
      RAISE EXCEPTION 'Sealed hash differs from stored content' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER decision_snapshots_sealed AFTER INSERT OR UPDATE ON app.decision_snapshots
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_sealed_snapshot();

CREATE FUNCTION app.capture_line(line_id uuid,actor uuid) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
DECLARE line app.purchase_order_lines; supplier_head uuid; department_head uuid;
  snapshot uuid:=gen_random_uuid(); instant timestamptz(3);
BEGIN
  PERFORM app.require_read_committed();
  PERFORM app.require_actor(actor);
  -- Deterministic lock order within a single-root capture: line → supplier → department.
  SELECT * INTO line FROM app.purchase_order_lines WHERE id=line_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Line absent' USING ERRCODE='23503'; END IF;
  IF line.supplier_id IS NOT NULL THEN
    SELECT current_version_id INTO supplier_head FROM app.suppliers WHERE id=line.supplier_id FOR SHARE;
  END IF;
  IF line.department_id IS NOT NULL THEN
    SELECT current_version_id INTO department_head FROM app.departments WHERE id=line.department_id FOR SHARE;
  END IF;
  -- The locked line cannot change its relationships; context heads were read under their locks.
  PERFORM app.validate_projection('purchase_order_line',line.id);
  IF line.supplier_id IS NOT NULL THEN PERFORM app.validate_projection('supplier',line.supplier_id); END IF;
  IF line.department_id IS NOT NULL THEN PERFORM app.validate_projection('department',line.department_id); END IF;
  instant:=clock_timestamp();
  INSERT INTO app.decision_snapshots(id,root_record_version_id,actor_user_id,knowledge_cutoff_at,captured_at)
    VALUES(snapshot,line.current_version_id,actor,instant,instant);
  INSERT INTO app.snapshot_members(snapshot_id,record_version_id,purchase_line_owner_id,role)
    VALUES(snapshot,line.current_version_id,line.id,'root');
  IF supplier_head IS NOT NULL THEN
    INSERT INTO app.snapshot_members(snapshot_id,record_version_id,supplier_owner_id,role)
      VALUES(snapshot,supplier_head,line.supplier_id,'supplier_context');
  END IF;
  IF department_head IS NOT NULL THEN
    INSERT INTO app.snapshot_members(snapshot_id,record_version_id,department_owner_id,role)
      VALUES(snapshot,department_head,line.department_id,'department_context');
  END IF;
  PERFORM app.validate_snapshot_members(snapshot);
  INSERT INTO app.audit_events(actor_user_id,operation,snapshot_id,context)
    VALUES(actor,'capture',snapshot,jsonb_build_object('database_session',session_user));
  RETURN snapshot;
END $$;

CREATE FUNCTION app.seal_snapshot(snapshot uuid,actor uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,app AS $$
DECLARE state text; digest text;
BEGIN
  PERFORM app.require_read_committed();
  PERFORM app.require_actor(actor);
  SELECT status INTO state FROM app.decision_snapshots WHERE id=snapshot FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Snapshot absent' USING ERRCODE='23503'; END IF;
  IF state<>'draft' THEN RAISE EXCEPTION 'Snapshot already sealed' USING ERRCODE='55000'; END IF;
  -- Separate statements after obtaining the lock see committed member changes under READ COMMITTED.
  PERFORM app.validate_snapshot_members(snapshot);
  digest:=app.snapshot_digest(snapshot);
  UPDATE app.decision_snapshots SET status='sealed',content_hash=digest,sealed_at=clock_timestamp() WHERE id=snapshot;
  INSERT INTO app.audit_events(actor_user_id,operation,snapshot_id,context)
    VALUES(actor,'seal',snapshot,jsonb_build_object('database_session',session_user));
  RETURN digest;
END $$;

-- Immutable evidence, plus TRUNCATE guards (row triggers alone do not guard TRUNCATE).
DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['record_versions','source_references','audit_events'] LOOP
    EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.deny_mutation()',table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['currencies','suppliers','departments','purchase_order_lines',
    'source_identities','decision_snapshots'] LOOP
    EXECUTE format('CREATE TRIGGER preserve_rows BEFORE DELETE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.deny_mutation()',table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['currencies','users','suppliers','departments','purchase_order_lines',
    'source_identities','source_references','record_versions','decision_snapshots','snapshot_members','audit_events'] LOOP
    EXECUTE format('CREATE TRIGGER preserve_table BEFORE TRUNCATE ON app.%I FOR EACH STATEMENT EXECUTE FUNCTION app.deny_mutation()',table_name);
  END LOOP;
END $$;
CREATE TRIGGER currencies_immutable BEFORE UPDATE ON app.currencies
  FOR EACH ROW EXECUTE FUNCTION app.deny_mutation();

-- Fail closed: no runtime role is invented or granted by this migration.
-- Migration owner/admin can alter schema/triggers; it must NEVER be the application identity.
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

COMMIT;
