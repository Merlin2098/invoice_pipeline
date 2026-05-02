from src.jobs.example_job import build_job_plan, load_config


def test_load_config_reads_expected_job_name() -> None:
    config = load_config()
    assert config.job_name == "orders_curated"
    assert config.transformation_sql.endswith(".sql")


def test_build_job_plan_embeds_sql_and_contract() -> None:
    plan = build_job_plan(load_config())
    assert "select" in plan["transformation_sql"].lower()
    assert plan["contract"]["dataset"] == "curated.orders"
