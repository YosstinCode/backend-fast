from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus

app = FastAPI()

# config cors
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class ValidCombination(BaseModel):
    combination: str
    description: str
    capacity: int
    cost: int

class Customer(BaseModel):
    client: str
    Cleveland: float
    Harrisburg: float
    Chicago: float
    Trenton: float
    Louisville: float
    demand: int

class Location(BaseModel):
    location: str
    capacity: int
    shippingCost: float
    generalCost: int

class TransportationData(BaseModel):
    validCombinations: List[ValidCombination]
    customers: List[Customer]
    locations: List[Location]

# Helper Function to transform data
def transform_data_to_cost_matrix(customers: List[Customer], locations: List[Location]) -> Dict[str, Dict[str, float]]:
    # Map locations to their shipping costs
    shipping_costs = {loc.location: loc.shippingCost for loc in locations}

    # Initialize the cost matrix
    cost_matrix = {loc.location: {} for loc in locations}

    # Fill the cost matrix with adjusted costs (client cost + shippingCost)
    for customer in customers:
        client_name = customer.client
        for loc in cost_matrix:
            # Sum the customer-specific cost and the location's shipping cost
            cost_matrix[loc][client_name] = getattr(customer, loc) + shipping_costs[loc]

    # Add the fictitious client with 0 cost for all locations
    for loc in cost_matrix:
        cost_matrix[loc]["Cliente fic."] = 0.0

    return cost_matrix

@app.post("/solve-transportation/")
def solve_transportation(data: TransportationData):
    try:
        # Transform data
        costos = transform_data_to_cost_matrix(data.customers, data.locations)
        oferta = {loc.location: loc.capacity for loc in data.locations}
        demanda = {customer.client: customer.demand for customer in data.customers}
        demanda["Cliente fic."] = sum(oferta.values()) - sum(demanda.values())

        # Create the model
        modelo = LpProblem("Problema_de_Transporte", LpMinimize)

        # Decision variables
        variables = {
            (almacen, cliente): LpVariable(f"x_{almacen}_{cliente}", lowBound=0, cat="Continuous")
            for almacen in oferta
            for cliente in demanda
        }

        # Objective function
        modelo += lpSum(variables[almacen, cliente] * costos[almacen][cliente] for almacen in oferta for cliente in demanda)

        # Supply constraints
        for almacen in oferta:
            modelo += lpSum(variables[almacen, cliente] for cliente in demanda) <= oferta[almacen], f"Oferta_{almacen}"

        # Demand constraints
        for cliente in demanda:
            modelo += lpSum(variables[almacen, cliente] for almacen in oferta) == demanda[cliente], f"Demanda_{cliente}"

        # Solve the model
        modelo.solve()

        # Generate the result matrix
        result_matrix = []
        for cliente in demanda:
            row = {"CLIENTE": cliente}
            total = 0
            for almacen in oferta:
                value = variables[almacen, cliente].value()
                row[almacen] = value if value else 0
                total += row[almacen]
            row["DEMANDA"] = total
            result_matrix.append(row)

        # Add capacity row
        capacity_row = {"CLIENTE": "CAPACIDAD"}
        total_capacity = 0
        for almacen in oferta:
            capacity_row[almacen] = oferta[almacen]
            total_capacity += oferta[almacen]
        capacity_row["DEMANDA"] = f"{total_capacity} / {sum(demanda.values())}"
        result_matrix.append(capacity_row)

        return {"status": LpStatus[modelo.status], "matrix": result_matrix, "total_cost": modelo.objective.value()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
