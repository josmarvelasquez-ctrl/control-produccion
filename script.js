let currentSlide = 0;
const totalSlides = document.querySelectorAll('.carousel-item').length;

/**
 * Mueve el carrusel en una dirección (+1 o -1)
 */
function moveCarousel(direction) {
    currentSlide = (currentSlide + direction + totalSlides) % totalSlides;
    updateUI();
}

/**
 * Va a un slide específico
 */
function goToSlide(index) {
    currentSlide = index;
    updateUI();
}

/**
 * Actualiza la posición visual y los puntos
 */
function updateUI() {
    const wrapper = document.getElementById('carouselWrapper');
    const dots = document.querySelectorAll('.dot');
    
    // Desplazamiento del wrapper
    wrapper.style.transform = `translateX(-${currentSlide * 100}%)`;
    
    // Actualización de los indicadores (dots)
    dots.forEach((dot, index) => {
        if (index === currentSlide) {
            dot.classList.add('active');
        } else {
            dot.classList.remove('active');
        }
    });
}

/**
 * Auto-reproducción automática cada 6 segundos
 */
let autoPlay = setInterval(() => {
    moveCarousel(1);
}, 6000);

// Detener auto-play si el usuario hace clic manualmente
const carouselContainer = document.querySelector('.carousel-container');
if (carouselContainer) {
    carouselContainer.addEventListener('mouseenter', () => {
        clearInterval(autoPlay);
    });
    carouselContainer.addEventListener('mouseleave', () => {
        clearInterval(autoPlay);
        autoPlay = setInterval(() => {
            moveCarousel(1);
        }, 6000);
    });
}