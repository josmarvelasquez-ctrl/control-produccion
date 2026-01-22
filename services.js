const servicesData = {
    'diseno': {
        title: 'Diseño Gráfico & Branding',
        image: 'img/branding.png',
        description: 'Creamos identidades visuales que perduran. Nuestro enfoque en el Arte Final garantiza que lo que ves en pantalla es exactamente lo que obtienes impreso.',
        details: `
            <p>El diseño gráfico no es solo estética, es comunicación estratégica. En Jota Studio nos especializamos en:</p>
            <ul class="list-disc pl-5 mt-4 space-y-2 text-slate-400">
                <li><strong>Branding e Identidad:</strong> Creación de logotipos, paletas de color y tipografías que definen tu marca.</li>
                <li><strong>Manuales de Marca:</strong> Guías técnicas para el uso correcto de tu imagen corporativa.</li>
                <li><strong>Diseño Editorial:</strong> Revistas, catálogos y folletos diagramados con precisión.</li>
                <li><strong>Arte Final:</strong> Preparación técnica de archivos para imprenta (separación de colores, troqueles, demasías).</li>
            </ul>
        `,
        gallery: [
            'https://images.unsplash.com/photo-1626785774573-4b799315545d?w=400&h=300&fit=crop',
            'https://images.unsplash.com/photo-1558655146-d09347e92766?w=400&h=300&fit=crop',
            'https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=400&h=300&fit=crop'
        ]
    },
    'impresion': {
        title: 'Impresión Variable Industrial',
        image: 'img/Impresora-termica.webp',
        description: 'Soluciones industriales para etiquetado y trazabilidad. Control total sobre tus datos variables.',
        details: `
            <p>La impresión de datos variables es crucial para la logística moderna. Ofrecemos:</p>
            <ul class="list-disc pl-5 mt-4 space-y-2 text-slate-400">
                <li><strong>Etiquetas de Código de Barras:</strong> EAN-13, UPC, Code 128, garantizando lectura perfecta.</li>
                <li><strong>Códigos QR Dinámicos:</strong> Enlaces a menús, webs o fichas técnicas.</li>
                <li><strong>Serialización:</strong> Numeración consecutiva para control de inventario o lotes.</li>
                <li><strong>Impresión Térmica:</strong> Alta durabilidad y resistencia para entornos industriales.</li>
            </ul>
        `,
        gallery: [
            'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=400&h=300&fit=crop',
            'https://images.unsplash.com/photo-1565514020176-dbf2277e4954?w=400&h=300&fit=crop'
        ]
    },
    'video': {
        title: 'Video Ads & Motion Graphics',
        image: 'img/video_ads.png',
        description: 'Edición dinámica diseñada para captar la atención en los primeros segundos.',
        details: `
            <p>El video es el rey del contenido en redes sociales. Potencia tu marca con:</p>
            <ul class="list-disc pl-5 mt-4 space-y-2 text-slate-400">
                <li><strong>Reels y TikToks:</strong> Edición rápida, subtítulos dinámicos y música en tendencia.</li>
                <li><strong>Motion Graphics:</strong> Animación de logotipos y elementos gráficos para explicar servicios complejos.</li>
                <li><strong>Videos Corporativos:</strong> Presentaciones profesionales de tu empresa o producto.</li>
            </ul>
        `,
        gallery: [
            'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=400&h=300&fit=crop',
            'https://images.unsplash.com/photo-1536240478700-b869070f9279?w=400&h=300&fit=crop'
        ]
    },
    'web': {
        title: 'Diseño Web & Desarrollo',
        image: 'img/high-angle-hands-holding-paper.jpg',
        description: 'Sitios web que no solo se ven bien, sino que convierten visitantes en clientes.',
        details: `
            <p>Tu web es tu oficina digital abierta 24/7. Desarrollamos:</p>
            <ul class="list-disc pl-5 mt-4 space-y-2 text-slate-400">
                <li><strong>Landing Pages:</strong> Páginas de aterrizaje optimizadas para campañas publicitarias.</li>
                <li><strong>Sitios Corporativos:</strong> Presencia digital sólida para empresas.</li>
                <li><strong>Diseño Responsive:</strong> Adaptación perfecta a móviles, tablets y escritorio.</li>
                <li><strong>Optimización SEO:</strong> Estructura técnica para mejorar tu posición en Google.</li>
            </ul>
        `,
        gallery: [
            'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=400&h=300&fit=crop',
            'https://images.unsplash.com/photo-1547658719-da2b51169166?w=400&h=300&fit=crop'
        ]
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const serviceDetailsContainer = document.getElementById('service-details');
    const params = new URLSearchParams(window.location.search);
    const serviceId = params.get('service');
    const service = servicesData[serviceId];

    if (service) {
        serviceDetailsContainer.innerHTML = `
            <div class="service-header" style="background-image: url('${service.image}')">
                <div class="service-header-overlay">
                    <h1 class="service-title">${service.title}</h1>
                </div>
            </div>
            <div class="service-content">
                <p class="service-description">${service.description}</p>
                <div class="service-details-body">${service.details}</div>
                <h2 class="gallery-title">Galería de Proyectos</h2>
                <div class="gallery">
                    ${service.gallery.map(img => `<img src="${img}" alt="Proyecto de ${service.title}">`).join('')}
                </div>
                <div class="cta-section">
                    <a href="https://wa.me/573022985621?text=Hola%20Jota%2C%20estoy%20interesado%20en%20el%20servicio%20de%20${service.title}" class="cta-whatsapp">
                        <i class="fab fa-whatsapp"></i> COTIZAR ESTE SERVICIO
                    </a>
                </div>
            </div>
        `;
    } else {
        serviceDetailsContainer.innerHTML = '<h1 class="service-title text-center">Servicio no encontrado</h1>';
    }
});