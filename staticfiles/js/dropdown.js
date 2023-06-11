const dropdowns = document.querySelectorAll('.dropdown-main')
console.log("Tlačítko dropdown")
dropdowns.forEach(dropdown => {
    const btn = dropdown.querySelector('.dropdown-btn')
    const content = dropdown.querySelector('.dropdown-content')
    
    btn.addEventListener('click', () => {
        content.classList.toggle('hidden')
        btn.classList.toggle('bg-white')
        btn.classList.toggle('text-green-600')
        console.log(btn.classList)
    })

    document.body.addEventListener('click', (e) => {
        if(e.target.classList.contains('dropdown-btn')) return
        content.classList.add('hidden')
        btn.classList.remove('bg-white')
        btn.classList.remove('text-green-600')
    })
})

console.log("Script Dropdown nahrán v delší verzi")