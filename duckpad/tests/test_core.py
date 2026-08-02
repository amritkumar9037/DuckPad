import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from duckpad import parser, schema, db


class TestParser(unittest.TestCase):
    def test_detects_tab_delimiter(self):
        text = "ID\tName\tDepartment\n1\tAlice\tHR\n2\tBob\tFinance"
        self.assertEqual(parser.detect_delimiter(text), "\t")

    def test_detects_comma_delimiter(self):
        text = "id,name,age\n1,Alice,30\n2,Bob,25"
        self.assertEqual(parser.detect_delimiter(text), ",")

    def test_detects_pipe_delimiter(self):
        text = "id|name|age\n1|Alice|30\n2|Bob|25"
        self.assertEqual(parser.detect_delimiter(text), "|")

    def test_header_detected_on_two_data_rows(self):
        # This is the exact scenario from the user's addendum -- must work
        # with only 2 data rows, not just when there's a large sample.
        rows = parser.split_rows("ID\tName\tDepartment\n1\tAlice\tHR\n2\tBob\tFinance", "\t")
        self.assertTrue(parser.detect_header(rows))

    def test_header_not_detected_when_absent(self):
        rows = parser.split_rows("1\t2\t3\n4\t5\t6\n7\t8\t9", "\t")
        self.assertFalse(parser.detect_header(rows))


class TestSchema(unittest.TestCase):
    def test_infers_integer(self):
        self.assertEqual(schema.infer_column_type(["1", "2", "3"]), schema.INTEGER)

    def test_infers_real_when_mixed_with_int(self):
        self.assertEqual(schema.infer_column_type(["1", "2.5", "3"]), schema.REAL)

    def test_infers_text_for_names(self):
        self.assertEqual(schema.infer_column_type(["Alice", "Bob"]), schema.TEXT)

    def test_infers_date(self):
        self.assertEqual(schema.infer_column_type(["2024-01-01", "2024-02-15"]), schema.DATE)

    def test_null_then_int_is_integer(self):
        self.assertEqual(schema.infer_column_type(["", "5", "6"]), schema.INTEGER)

    def test_all_empty_column_falls_back_to_text(self):
        self.assertEqual(schema.infer_column_type(["", "", ""]), schema.TEXT)


class TestDb(unittest.TestCase):
    def setUp(self):
        self.d = db.Database()

    def test_paste_as_table_full_workflow(self):
        # The exact "Paste as Table" scenario from the user's addendum:
        # paste Excel-style data -> table1 created -> SELECT * FROM table1 works.
        raw = "ID\tName\tDepartment\n1\tAlice\tHR\n2\tBob\tFinance\n"
        delim = parser.detect_delimiter(raw)
        rows = parser.split_rows(raw, delim)
        has_header = parser.detect_header(rows)
        self.assertTrue(has_header)
        header, data = rows[0], rows[1:]

        columns = []
        for i, col_name in enumerate(header):
            values = [r[i] for r in data]
            inferred = schema.infer_column_type(values)
            columns.append((db.safe_identifier(col_name, i + 1), inferred))

        name = self.d.next_scratch_name()
        self.assertEqual(name, "table1")
        info = self.d.import_table(name, columns, data)
        self.assertEqual(info.name, "table1")

        result = self.d.execute_sql("SELECT * FROM table1;")
        self.assertEqual(result.columns, ["ID", "Name", "Department"])
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0], [1, "Alice", "HR"])

    def test_scratch_names_increment(self):
        self.d.import_table(None, [("x", schema.INTEGER)], [["1"]])
        self.d.import_table(None, [("x", schema.INTEGER)], [["2"]])
        name = self.d.next_scratch_name()
        self.assertEqual(name, "table3")

    def test_invalid_sql_raises_not_crashes(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.d.execute_sql("SELEKT not valid sql;")

    def test_ddl_then_select_multi_statement(self):
        result = self.d.execute_sql(
            "CREATE TABLE sales(id INTEGER, amount REAL); "
            "INSERT INTO sales VALUES (1, 9.5); "
            "SELECT * FROM sales;"
        )
        self.assertEqual(result.columns, ["id", "amount"])
        self.assertEqual(result.rows, [[1, 9.5]])
        names = [t.name for t in self.d.get_schema()]
        self.assertIn("sales", names)

    def test_drop_table_updates_schema(self):
        self.d.execute_sql("CREATE TABLE temp_tbl(x INTEGER);")
        self.assertIn("temp_tbl", [t.name for t in self.d.get_schema()])
        self.d.execute_sql("DROP TABLE temp_tbl;")
        self.assertNotIn("temp_tbl", [t.name for t in self.d.get_schema()])

    def test_reimport_same_name_replaces(self):
        self.d.import_table("dup", [("x", schema.INTEGER)], [["1"]])
        self.d.import_table("dup", [("x", schema.INTEGER)], [["2"]])
        result = self.d.execute_sql("SELECT * FROM dup;")
        self.assertEqual(result.rows, [[2]])


import sqlite3  # noqa: E402  (used in TestDb.test_invalid_sql_raises_not_crashes)

if __name__ == "__main__":
    unittest.main()
