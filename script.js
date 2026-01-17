let usuarioIdActual = null;
let html5QrCode = null;
let filaDestinoActual = null;
let servicioSeleccionado = null;


function iniciarSesion() {
    const nombre = document.getElementById('login-nombre').value;
    const pass = document.getElementById('login-pass').value;

    if (!nombre || !pass) {
        alert("Por favor, ingrese su nombre y contraseña.");
        return;
    }

    fetch('http://127.0.0.1:5000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre: nombre, password: pass })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            usuarioIdActual = data.id_usuario;
            localStorage.setItem('usuarioId', data.id_usuario);
            localStorage.setItem('usuarioNombre', data.nombre);
            mostrarPanelAsistencia(data.nombre);
        } else {
            alert("Acceso denegado: " + data.message);
        }
    });
}

function mostrarPanelAsistencia(nombre) {
    document.getElementById('user-display').textContent = "Jefe: " + nombre;
    document.getElementById('auth-section').style.display = 'none';
    document.getElementById('attendance-section').style.display = 'block';
}

// MODIFICADO: Ahora incluye campos ocultos y el nombre es readonly
function agregarFila() {
    const contenedor = document.getElementById('lista-integrantes');
    const div = document.createElement('div');
    div.className = 'fila-trabajador';
    
    div.innerHTML = `
        <input type="text" class="integrante-nombre" placeholder="Nombre (vía QR)" readonly>
        <input type="hidden" class="integrante-dni">
        <input type="hidden" class="integrante-cargo">
        <button class="btn-scan" onclick="abrirEscanner(this)" title="Escanear QR">📷</button>
        <button class="btn-remove" onclick="this.parentElement.remove()" title="Quitar">×</button>
    `;
    contenedor.appendChild(div);
}

// MODIFICADO: Procesa la cadena separada por comas
async function abrirEscanner(boton) {
    const fila = boton.parentElement;
    const inputNombre = fila.querySelector('.integrante-nombre');
    const inputDni = fila.querySelector('.integrante-dni');
    const inputCargo = fila.querySelector('.integrante-cargo');

    document.getElementById('qr-modal').style.display = 'flex';
    
    html5QrCode = new Html5Qrcode("reader");
    try {
        await html5QrCode.start(
            { facingMode: "environment" },
            { fps: 10, qrbox: { width: 250, height: 250 } },
            (decodedText) => {
                // Formato esperado: Mario Gomez, 719867345, Supervisor
                const datos = decodedText.split(',');
                if(datos.length === 3) {
                    inputNombre.value = datos[0].trim();
                    inputDni.value = datos[1].trim();
                    inputCargo.value = datos[2].trim();
                } else {
                    alert("Formato de QR no válido. Debe ser: Nombre, DNI, Cargo");
                }
                cerrarEscanner();
            }
        );
    } catch (err) {
        console.error("Error:", err);
        alert("Cámara no disponible");
        cerrarEscanner();
    }
}

async function cerrarEscanner() {
    if (html5QrCode) {
        try {
            await html5QrCode.stop();
            await html5QrCode.clear();
        } catch (err) {
            console.log("Cámara ya estaba cerrada.");
        }
        html5QrCode = null;
    }
    document.getElementById('qr-modal').style.display = 'none';
}

function irAPaso(paso) {
    if (paso === 2) {
        const nombres = Array.from(document.querySelectorAll('.integrante-nombre')).map(i => i.value);
        if (nombres.filter(n => n.trim() !== "").length === 0) {
            alert("Agregue al menos un integrante.");
            return;
        }
        document.getElementById('paso-1').style.display = 'none';
        document.getElementById('paso-2').style.display = 'block';
    } else {
        document.getElementById('paso-2').style.display = 'none';
        document.getElementById('paso-1').style.display = 'block';
    }
}

function obtenerUbicacion() {
    const status = document.getElementById('status-msg');
    const foto1 = document.getElementById('foto-grupo').files[0];
    const foto2 = document.getElementById('foto-doc').files[0];

    if (!foto1 || !foto2) {
        alert("Ambas fotos son obligatorias.");
        return;
    }

    status.textContent = "Obteniendo ubicación GPS...";
    navigator.geolocation.getCurrentPosition(
        (pos) => enviarTodo(pos.coords.latitude, pos.coords.longitude),
        (err) => status.textContent = "Error: Active el GPS."
    );
}

// MODIFICADO: Envía objetos completos (Nombre, DNI, Cargo)
async function enviarTodo(lat, lon) {
    const status = document.getElementById('status-msg');
    const formData = new FormData();
    
    if (!usuarioIdActual) {
         usuarioIdActual = localStorage.getItem('usuarioId');
    }
    const tipoEvento = document.querySelector('input[name="tipo_evento"]:checked').value;

    // Recolectamos todos los campos de cada integrante
    const filas = document.querySelectorAll('.fila-trabajador');
    const integrantes = [];

    filas.forEach(fila => {
        const nombre = fila.querySelector('.integrante-nombre').value;
        const dni = fila.querySelector('.integrante-dni').value;
        const cargo = fila.querySelector('.integrante-cargo').value;

        if (nombre.trim() !== "") {
            integrantes.push({
                nombre: nombre,
                dni: dni,
                cargo: cargo
            });
        }
    });

    formData.append('id_lider', usuarioIdActual);
    formData.append('tipo_evento', tipoEvento);
    formData.append('oc_referencia', servicioSeleccionado);
    formData.append('integrantes', JSON.stringify(integrantes));
    formData.append('lat', lat);
    formData.append('lon', lon);
    formData.append('foto_grupal', document.getElementById('foto-grupo').files[0]);
    formData.append('foto_documento', document.getElementById('foto-doc').files[0]);
    

    status.textContent = `Enviando reporte de ${tipoEvento}...`;
    try {
        const res = await fetch('http://127.0.0.1:5000/registrar_grupal', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if(data.status === "ok") {
            
            status.style.color = "#00ff88";
            status.textContent = `✅ ${tipoEvento} Guardada correctamente.`;
            if (data.alerta) {
                alert("AVISO: " + data.alerta);
            }
            setTimeout(() => location.reload(), 3000);
        }

    } catch (e) {
        status.style.color = "#ff4d4d";
        status.textContent = "❌ Error al conectar con el servidor.";
    }

}

document.getElementById('input-oc').addEventListener('input', async function () {
       const q = this.value;
       const cont = document.getElementById('oc-sugerencias');
       cont.innerHTML = "";

       if (q.length < 2) return;

       const res = await fetch(`http://127.0.0.1:5000/servicios/buscar?q=${q}`);
       const data = await res.json();

       data.forEach(s => {
           const div = document.createElement('div');
           div.className = 'sugerencia-item';
           div.innerHTML = `<b>${s.oc}</b> — ${s.cliente}`;
           div.onclick = () => {
               document.getElementById('input-oc').value = s.oc;
               servicioSeleccionado = s.oc;
               cont.innerHTML = "";
            };
            cont.appendChild(div);
        });
    });

function confirmarServicio() {
    if (!servicioSeleccionado) {
        alert("Seleccione un servicio válido");
        return;
    }

    document.getElementById('paso-0').style.display = 'none';
    document.getElementById('paso-1').style.display = 'block';
}

let ocActual = '';

async function filtrarPorOC() {
    ocActual = document.getElementById('buscarOC').value.trim();

    if (!ocActual) {
        alert('Ingrese una OC');
        return;
    }

    const response = await fetch(`http://127.0.0.1:5000/admin/get_all`);
    const datos = await response.json();

    const filtrados = datos.filter(a => a.servicio.oc === ocActual);

    renderTabla(filtrados);
}

function descargarExcel() {
    if (!ocActual) {
        alert('Primero filtre por OC');
        return;
    }

    window.open(
        `http://127.0.0.1:5000/admin/export_excel?oc=${ocActual}`,
        '_blank'
    );
}


