-- question-images 上线迁移（MySQL 生产库，手动执行一次）
--
-- 背景：SQLAlchemy create_all(checkfirst=True) 只新建缺失的表，不会给已存在的
-- 表补列。image_gen_usage 是新表，由应用启动 init_db 自动创建，无需手动处理；
-- 但 quiz_record_items 是既有表，新增的 image_url 列需要手动 ALTER 补齐。
--
-- 执行前建议先备份该表。列带 NOT NULL DEFAULT ''，对既有行安全（回填空串）。

ALTER TABLE quiz_record_items
    ADD COLUMN image_url VARCHAR(500) NOT NULL DEFAULT '';

-- image_gen_usage 由 create_all 自动建表；若需手动建表可参考：
-- CREATE TABLE image_gen_usage (
--     id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
--     user_id BIGINT UNSIGNED NOT NULL,
--     usage_date DATE NOT NULL,
--     count INT UNSIGNED NOT NULL DEFAULT 0,
--     PRIMARY KEY (id),
--     UNIQUE KEY uq_image_usage_user_date (user_id, usage_date),
--     CONSTRAINT fk_image_usage_user FOREIGN KEY (user_id) REFERENCES users (id)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
