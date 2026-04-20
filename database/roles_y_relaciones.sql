ALTER TABLE pacientes
    ADD COLUMN IF NOT EXISTS PacTipoSangre VARCHAR(10) NULL,
    ADD COLUMN IF NOT EXISTS PacAlergias TEXT NULL,
    ADD COLUMN IF NOT EXISTS PacPeso DECIMAL(5,2) NULL;

CREATE TABLE IF NOT EXISTS usuarios (
    UsuCodigo INT AUTO_INCREMENT PRIMARY KEY,
    PacCodigo INT NULL UNIQUE,
    DocCodigo INT NULL UNIQUE,
    UsuNombre VARCHAR(120) NOT NULL,
    UsuUsername VARCHAR(80) NOT NULL UNIQUE,
    UsuCorreo VARCHAR(120) NULL,
    UsuPasswordHash VARCHAR(255) NOT NULL,
    UsuRol ENUM('admin', 'paciente', 'doctor') NOT NULL DEFAULT 'paciente',
    UsuActivo TINYINT(1) NOT NULL DEFAULT 1,
    FechaCreacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuarios_pacientes
        FOREIGN KEY (PacCodigo) REFERENCES pacientes(PacCodigo)
        ON DELETE SET NULL,
    CONSTRAINT fk_usuarios_doctores
        FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS citas (
    CitCodigo INT AUTO_INCREMENT PRIMARY KEY,
    PacCodigo INT NOT NULL,
    DocCodigo INT NOT NULL,
    CitFecha DATE NOT NULL,
    CitHora TIME NOT NULL,
    CitEstado VARCHAR(30) NOT NULL DEFAULT 'Programada',
    CitMotivo VARCHAR(150) NOT NULL,
    CitObservaciones TEXT NULL,
    CONSTRAINT fk_citas_pacientes
        FOREIGN KEY (PacCodigo) REFERENCES pacientes(PacCodigo)
        ON DELETE CASCADE,
    CONSTRAINT fk_citas_doctores
        FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS historial_clinico (
    HcCodigo INT AUTO_INCREMENT PRIMARY KEY,
    CitCodigo INT NOT NULL UNIQUE,
    HcDiagnostico TEXT NOT NULL,
    HcTratamiento TEXT NULL,
    HcObservaciones TEXT NULL,
    HcFechaRegistro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_historial_citas
        FOREIGN KEY (CitCodigo) REFERENCES citas(CitCodigo)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS horarios_medicos (
    HorCodigo INT AUTO_INCREMENT PRIMARY KEY,
    DocCodigo INT NOT NULL,
    HorDiaSemana VARCHAR(15) NOT NULL,
    HorHoraInicio TIME NOT NULL,
    HorHoraFin TIME NOT NULL,
    HorActivo TINYINT(1) NOT NULL DEFAULT 1,
    CONSTRAINT fk_horarios_doctores
        FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
        ON DELETE CASCADE
);

INSERT INTO usuarios (
    PacCodigo,
    UsuNombre,
    UsuUsername,
    UsuCorreo,
    UsuPasswordHash,
    UsuRol,
    UsuActivo
) VALUES (
    NULL,
    'Administrador Principal',
    'admin',
    'admin@prohospital.local',
    'REEMPLAZA_AQUI_EL_HASH',
    'admin',
    1
);
