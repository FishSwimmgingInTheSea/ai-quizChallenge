-- 智趣 AI 闯关学习小程序 —— 数据库建表脚本（MySQL 8.0）
--
-- 本文件与 backend/app/db/orm_models.py 的 ORM 模型、以及生产库真实结构一致，
-- 供手动初始化/校验生产库使用；应用启动 init_db 会执行 create_all(checkfirst=True)
-- 自动建缺失表。向量本体存于 Chroma，此处只存元信息与状态。
--
-- 说明：约束名沿用生产库真实命名——users / quiz_records 为手动建表带显式名
-- （uk_* / fk_*），其余表由 SQLAlchemy create_all 建表，MySQL 自动分配 *_ibfk_1。
--
-- 约定：InnoDB 引擎 + utf8mb4 字符集；时间列由数据库默认值维护。
-- 执行前请确认已创建目标库（默认库名 ai_quiz）：
--   CREATE DATABASE IF NOT EXISTS ai_quiz DEFAULT CHARSET utf8mb4;
--   USE ai_quiz;

-- ---------------------------------------------------------------------------
-- users：用户表
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    openid      VARCHAR(64)     NOT NULL COMMENT '微信 openid；dev 模式为固定开发标识',
    nickname    VARCHAR(32)     NOT NULL DEFAULT '学习小达人',
    avatar_url  VARCHAR(255)    NOT NULL DEFAULT '' COMMENT '头像 URL（本地静态路径或对象存储 URL）',
    total_xp    INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '累计经验值（服务端权威）',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uk_users_openid UNIQUE (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- quiz_records：闯关记录表（每局一行）
-- ---------------------------------------------------------------------------
CREATE TABLE quiz_records (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           BIGINT UNSIGNED NOT NULL,
    client_record_id  VARCHAR(64)     NOT NULL COMMENT '前端每局生成的幂等键（UUID）',
    title             VARCHAR(100)    NOT NULL COMMENT '题库标题（主题）',
    question_count    SMALLINT UNSIGNED NOT NULL,
    correct_count     SMALLINT UNSIGNED NOT NULL,
    accuracy          SMALLINT UNSIGNED NOT NULL COMMENT '正确率 0-100，服务端复算',
    duration_ms       INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '本局总用时（毫秒）',
    xp_earned         SMALLINT UNSIGNED NOT NULL COMMENT '本局 XP，服务端复算',
    stars             TINYINT UNSIGNED NOT NULL COMMENT '星级 1-5，服务端复算',
    created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uk_records_client UNIQUE (client_record_id),
    CONSTRAINT fk_records_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_records_user_time ON quiz_records (user_id ASC, created_at DESC);

-- ---------------------------------------------------------------------------
-- quiz_record_items：题目记录表（每局每题一行，题快照 + 作答）
-- 注：image_url 为后补列（question-images 迁移 ALTER ADD），故置于末列。
-- ---------------------------------------------------------------------------
CREATE TABLE quiz_record_items (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    record_id         BIGINT UNSIGNED NOT NULL,
    question_index    SMALLINT UNSIGNED NOT NULL COMMENT '0-based，与提交顺序一致',
    question_id       VARCHAR(64)     NOT NULL,
    -- 题快照
    qtype             VARCHAR(16)     NOT NULL,
    difficulty        VARCHAR(16)     NOT NULL,
    knowledge_point   VARCHAR(100)    NOT NULL,
    stem              TEXT            NOT NULL,
    explanation       TEXT            NOT NULL,
    options           JSON            NOT NULL,
    answer            JSON            NOT NULL,
    -- 作答
    selected_answers  JSON            NOT NULL,
    is_correct        TINYINT(1)      NOT NULL COMMENT '服务端 judge_answer 复算值',
    duration_ms       INT UNSIGNED    NOT NULL DEFAULT 0,
    image_url         VARCHAR(500)    NOT NULL DEFAULT '' COMMENT '配图永久 URL，无图空串',
    PRIMARY KEY (id),
    CONSTRAINT quiz_record_items_ibfk_1 FOREIGN KEY (record_id) REFERENCES quiz_records (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_items_record ON quiz_record_items (record_id);

-- ---------------------------------------------------------------------------
-- quiz_reports：报告表（与 quiz_records 一对一）
-- ---------------------------------------------------------------------------
CREATE TABLE quiz_reports (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    record_id           BIGINT UNSIGNED NOT NULL,
    user_id             BIGINT UNSIGNED NOT NULL,
    accuracy            SMALLINT UNSIGNED NOT NULL COMMENT '服务端复算覆盖',
    mastered_points     JSON            NOT NULL,
    weak_points         JSON            NOT NULL,
    three_line_summary  JSON            NOT NULL,
    advice              JSON            NOT NULL,
    share_quote         VARCHAR(255)    NOT NULL DEFAULT '',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT record_id UNIQUE (record_id),
    CONSTRAINT quiz_reports_ibfk_1 FOREIGN KEY (record_id) REFERENCES quiz_records (id),
    CONSTRAINT quiz_reports_ibfk_2 FOREIGN KEY (user_id)   REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_reports_user_time ON quiz_reports (user_id, created_at);

-- ---------------------------------------------------------------------------
-- kb_documents：知识库文档表（上传记录 + 处理状态机 + 入库统计）
-- ---------------------------------------------------------------------------
CREATE TABLE kb_documents (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id      BIGINT UNSIGNED NOT NULL,
    filename     VARCHAR(255)    NOT NULL,
    doc_type     VARCHAR(16)     NOT NULL COMMENT 'pdf / docx / md / txt',
    file_size    INT UNSIGNED    NOT NULL COMMENT '上传文件字节数',
    char_count   INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '解析后纯文本字符数',
    chunk_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '分块数',
    status       VARCHAR(16)     NOT NULL DEFAULT 'processing' COMMENT 'processing/ready/failed',
    error        VARCHAR(255)    NOT NULL DEFAULT '' COMMENT '失败原因，成功空串',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- updated_at 的刷新由 ORM onupdate=func.now() 在 UPDATE 语句层处理，
    -- create_all 不生成 DDL 的 ON UPDATE 子句，故此处与生产库一致不带 ON UPDATE。
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT kb_documents_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_kb_docs_user_time ON kb_documents (user_id, created_at);

-- ---------------------------------------------------------------------------
-- image_gen_usage：每人每日生图用量计数
-- ---------------------------------------------------------------------------
CREATE TABLE image_gen_usage (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED NOT NULL,
    usage_date  DATE            NOT NULL COMMENT '自然日，按服务器本地日期归属配额',
    count       INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '当日已生成配图张数',
    PRIMARY KEY (id),
    CONSTRAINT uq_image_usage_user_date UNIQUE (user_id, usage_date),
    CONSTRAINT image_gen_usage_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
