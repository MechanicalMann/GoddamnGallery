
-- Table: images
CREATE TABLE images ( 
    id      INTEGER         PRIMARY KEY AUTOINCREMENT,
    path    VARCHAR( 255 )  NOT NULL,
    thumb   VARCHAR( 255 ),
    gallery VARCHAR( 255 )  NOT NULL,
    parent  VARCHAR( 255 ),
    x       INTEGER,
    y       INTEGER,
    r       INTEGER,
    g       INTEGER,
    b       INTEGER
);

-- Table: tags
CREATE TABLE tags ( 
    id   INTEGER         PRIMARY KEY,
    name VARCHAR( 128 )  NOT NULL
                         UNIQUE,
    slug VARCHAR( 128 )  NOT NULL
                         UNIQUE 
);

-- Table: tag_image
CREATE TABLE tag_image ( 
    id       INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL
                     REFERENCES images ( id ) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL
                     REFERENCES tags ( id ) ON DELETE CASCADE 
);

-- View: images_by_tag
CREATE VIEW images_by_tag AS
       SELECT t.name AS tag_name,
              t.slug AS tag_slug,
              i.*
         FROM tags t
              LEFT JOIN tag_image ti
                     ON ti.tag_id = t.id
              LEFT JOIN images i
                     ON i.id = ti.image_id;
;


-- View: tags_by_image
CREATE VIEW tags_by_image AS
       SELECT i.path,
              t.*
         FROM images i
              LEFT JOIN tag_image ti
                     ON ti.image_id = i.id
              LEFT JOIN tags t
                     ON t.id = ti.tag_id;
;

