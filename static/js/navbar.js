//Profile
const profileBtn = document.querySelector('#user-menu-button')
const profileDropdown = document.querySelector('#profile-dropdown')
const elementsWithoutNav = document.querySelectorAll('body > :not(#navbar)')

profileBtn.addEventListener('click', () => profileDropdown.classList.toggle('hidden'))

elementsWithoutNav.forEach(el => el.addEventListener('click', () => {
    profileDropdown.classList.add('hidden')
    mobileNav.classList.add('hidden')
}))

//Mobile
const showNavBtn = document.querySelector('#show-mobile-nav-btn')
const mobileNav = document.querySelector('#mobile-menu')
const links = document.querySelectorAll('#navbar a')

showNavBtn.addEventListener('click', () => mobileNav.classList.toggle('hidden'))

links.forEach(link => link.addEventListener('click', () => mobileNav.classList.add('hidden')))