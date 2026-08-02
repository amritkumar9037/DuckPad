// AG Grid v31+ split the Community package into opt-in modules. Nothing
// is auto-registered anymore, so AgGridReact throws "error #200: Unable
// to use rowModelType 'clientSide' as it hasn't been registered" the
// instant it tries to mount with data -- which in this app means the
// first time a query result populates ResultsGrid, i.e. exactly when the
// user presses Run. Registering here, once, at app startup, fixes it.
//
// ClientSideRowModelModule: the row model ResultsGrid actually uses.
// CommunityFeaturesModule: bundles the other Community features this app
// turns on per-column (sortable, filter, editable) -- editing, filter,
// pagination, core-validations, etc.
import { ModuleRegistry, ClientSideRowModelModule, CommunityFeaturesModule } from "ag-grid-community";

ModuleRegistry.registerModules([ClientSideRowModelModule, CommunityFeaturesModule]);
