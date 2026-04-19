CREATE TABLE IF NOT EXISTS citas (
    CitCodigo INT AUTO_INCREMENT PRIMARY KEY,
    PacCodigo INT NOT NULL,
    DocCodigo INT NOT NULL,
    CitFecha DATE NOT NULL,
    CitHora TIME NOT NULL,
    CitEstado VARCHAR(30) NOT NULL DEFAULT 'Programada',
    CitMotivo VARCHAR(150) NOT NULL,
    CitObservaciones TEXT NULL
);
