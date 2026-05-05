import { useState } from 'react';
import './App.css';
import AgentPanel from './components/AgentPanel';
import RegionDropdown from './components/RegionDropdown';
import TempLogoImage from './assets/templogo.png';

function ComponentTestingView() {
  const [region, setRegion] = useState('eu');

  return (
    <div className="App">
      <header className="App-header">
        <div className="component-test-view">
          <div className="component-test-header">
            <div>
              <p className="component-test-kicker">Component testing</p>
              <h1>RegionDropdown</h1>
            </div>
            <a className="component-test-link" href="/">
              Back to app
            </a>
          </div>
        </div>

      </header>
      <div className="App-main">
        <section className="component-test-stage" aria-label="RegionDropdown test stage">
          <RegionDropdown
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          />
          <p className="component-test-value">Selected value: {region}</p>
        </section>
      </div>
    </div>
  );
}

function App() {
  const searchParams = new URLSearchParams(window.location.search);
  const isComponentTestingView = searchParams.get('view') === 'components';

  if (isComponentTestingView) {
    return <ComponentTestingView />;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>OCP Policy Searcher</h1>
        <img src={TempLogoImage} alt="Temp Logo" className="logo-image" />
      </header>
      <main className="App-main">
        <a className="component-test-link app-dev-link" href="/?view=components">
          Components
        </a>
        <AgentPanel />
      </main>
    </div>
  );
}

export default App;
