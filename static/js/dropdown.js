const dropdowns = document.querySelectorAll('.dropdown-main')

dropdowns.forEach(dropdown => {
    const btn = dropdown.querySelector('.dropdown-btn')
    const content = dropdown.querySelector('.dropdown-content')
    
    btn.addEventListener('click', () => {
        content.classList.toggle('hidden')

    })

    document.body.addEventListener('click', (e) => {
        if(e.target.classList.contains('dropdown-btn')) return
        content.classList.add('hidden')

    })
})

console.log("Script Dropdown nahrán")