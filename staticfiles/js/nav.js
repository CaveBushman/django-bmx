const nav = document.querySelector('.nav2')
const showBtn = document.getElementById('menuBtn')
const mobileNav = document.querySelector('.nav2 ul')

window.addEventListener('scroll', updateNav)
showBtn.addEventListener('click', showNav)

function updateNav() {
    if(window.scrollY > nav.offsetHeight + 150) {
        nav.classList.add('active')
    } else {
        nav.classList.remove('active')
    }
}

function showNav() {
    nav.classList.toggle('mobile')
}