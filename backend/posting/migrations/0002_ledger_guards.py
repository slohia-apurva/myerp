"""Database guards for the two ledgers (design rules 2 and 4).

* Posted rows never change: UPDATE is refused on GL entries and stock moves,
  and DELETE unless the Owner's data reset has set myerp.purge_postings for
  its own transaction.
* Every voucher's GL rows balance: checked when the transaction commits, so a
  voucher's lines may be written one by one.
"""

from django.db import migrations

GUARD = """
CREATE OR REPLACE FUNCTION posting_refuse_change() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('myerp.purge_postings', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Posted ledger rows cannot be changed or deleted (%); cancel the entry instead.', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER posting_glentry_immutable BEFORE UPDATE OR DELETE ON posting_glentry
    FOR EACH ROW EXECUTE FUNCTION posting_refuse_change();
CREATE TRIGGER posting_stockmove_immutable BEFORE UPDATE OR DELETE ON posting_stockmove
    FOR EACH ROW EXECUTE FUNCTION posting_refuse_change();

CREATE OR REPLACE FUNCTION posting_check_balance() RETURNS trigger AS $$
DECLARE
    diff numeric;
BEGIN
    SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) INTO diff
      FROM posting_glentry
     WHERE company_id = NEW.company_id
       AND voucher_type = NEW.voucher_type
       AND voucher_id = NEW.voucher_id;
    IF diff <> 0 THEN
        RAISE EXCEPTION 'GL entries of % % do not balance (difference %).',
            NEW.voucher_type, NEW.voucher_no, diff;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER posting_glentry_balanced AFTER INSERT ON posting_glentry
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION posting_check_balance();
"""

UNGUARD = """
DROP TRIGGER IF EXISTS posting_glentry_balanced ON posting_glentry;
DROP FUNCTION IF EXISTS posting_check_balance();
DROP TRIGGER IF EXISTS posting_stockmove_immutable ON posting_stockmove;
DROP TRIGGER IF EXISTS posting_glentry_immutable ON posting_glentry;
DROP FUNCTION IF EXISTS posting_refuse_change();
"""


class Migration(migrations.Migration):
    dependencies = [("posting", "0001_initial")]

    operations = [migrations.RunSQL(GUARD, UNGUARD)]
