(() => {
  const roles = {admin: 'Administrator', developer: 'Developer'};
  let selected = null;
  function selectRole(role, move = false) {
    selected = Object.hasOwn(roles, role) ? role : null;
    document.querySelectorAll('[data-journey]').forEach(section => {
      section.hidden = section.dataset.journey !== selected;
    });
    document.querySelectorAll('[data-role-nav]').forEach(link => {
      link.hidden = link.dataset.roleNav !== selected;
    });
    document.querySelectorAll('[data-role-option]').forEach(option => {
      option.hidden = option.disabled = option.dataset.roleOption !== selected;
    });
    document.querySelectorAll('[data-role]').forEach(button => {
      const active = button.dataset.role === selected;
      button.setAttribute('aria-pressed', String(active));
      button.querySelector('.selection').textContent = active ? '✓ Selected — your setup below' : `Choose ${roles[button.dataset.role].toLowerCase()} →`;
    });
    document.querySelectorAll('.role-indicator').forEach(label => {
      label.textContent = selected ? `${roles[selected]} journey selected` : 'Choose your role to begin';
    });
    document.querySelector('.journey-bar').toggleAttribute('data-selected', !!selected);
    document.getElementById('section-select').value = selected || 'start';
    if (move && selected) {
      location.hash = selected;
      const section = document.getElementById(selected);
      section.setAttribute('tabindex', '-1');
      section.focus({preventScroll:true});
      section.scrollIntoView();
    }
  }
  document.querySelectorAll('[data-role]').forEach(button => {
    button.addEventListener('click', () => selectRole(button.dataset.role, true));
  });
  document.querySelector('[data-change-role]').addEventListener('click', event => {
    event.preventDefault();
    location.hash = 'start';
    document.getElementById('role-picker').scrollIntoView({block:'center'});
    document.querySelector('[data-role]').focus({preventScroll:true});
  });
  // Role-specific links intentionally select that journey. Ordinary visits have no default.
  function applyHash() {
    const target = location.hash.slice(1);
    if (Object.hasOwn(roles, target)) selectRole(target);
  }
  window.addEventListener('hashchange', applyHash);
  selectRole(null);
  applyHash();
})();
