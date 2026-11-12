"""GrowthCognix industry taxonomy v1: 25 major groups and their subcategories.

Reference data seeded by migration 0001. Add new industries with a new migration,
never by editing rows in place, so knowledge packs keep stable slugs.
"""

TAXONOMY: list[tuple[str, list[str]]] = [
    ("Agriculture and allied", ["Crop farming", "Seeds and fertilisers", "Agri equipment",
                               "Dairy and poultry", "Fisheries", "Horticulture and floriculture"]),
    ("Manufacturing", ["Steel and metals", "Machinery and equipment", "Plastics and polymers",
                       "Electrical and electronics", "Packaging", "Furniture"]),
    ("Chemicals and pharmaceuticals", ["Speciality chemicals", "Pharmaceutical manufacturing",
                                       "Paints and coatings", "Fertiliser manufacturing"]),
    ("Textiles and apparel", ["Textile mills", "Garment manufacturing", "Fashion brands",
                              "Handloom and handicrafts"]),
    ("Construction and infrastructure", ["Builders and contractors", "Architects and interiors",
                                         "Building materials", "Infrastructure projects"]),
    ("Real estate", ["Residential developers", "Commercial real estate", "Brokers and agents",
                     "Co-working and rentals"]),
    ("Healthcare", ["Hospitals", "Clinics", "Dental", "Diagnostics and labs",
                    "Ayurveda and wellness", "Medical devices"]),
    ("Education", ["Schools", "Colleges and universities", "Coaching and test prep",
                   "EdTech", "Skill development"]),
    ("Retail", ["Supermarkets and grocery", "Fashion retail", "Electronics retail",
                "Jewellery", "Home and furniture retail"]),
    ("Ecommerce and D2C", ["D2C brands", "Marketplace sellers", "Subscription commerce"]),
    ("Food and beverage", ["Restaurants and cafes", "Cloud kitchens", "Packaged foods",
                           "Bakeries and sweets", "Beverages", "Catering"]),
    ("Hospitality and tourism", ["Hotels and resorts", "Homestays", "Travel agencies",
                                 "Tour operators", "Event venues"]),
    ("Automobile", ["Car dealerships", "Two-wheeler dealerships", "Auto parts",
                    "Service and repair", "Electric vehicles"]),
    ("Transport and logistics", ["Freight and trucking", "Courier and delivery",
                                 "Warehousing", "Packers and movers"]),
    ("Banking and finance", ["Banks and NBFCs", "Wealth and investment advisory",
                             "Loans and credit", "Accounting and tax services"]),
    ("Insurance", ["Life insurance", "Health insurance", "General insurance",
                   "Insurance agents and brokers"]),
    ("IT and SaaS", ["SaaS products", "IT services", "Cybersecurity", "Cloud and hosting"]),
    ("Telecom and internet", ["Internet service providers", "Telecom services",
                              "Telecom equipment"]),
    ("Media and entertainment", ["Film and production", "Digital media and creators",
                                 "Publishing", "Events and entertainment"]),
    ("Professional services", ["Legal", "Consulting", "HR and recruitment",
                               "Marketing and advertising agencies"]),
    ("Beauty and personal care", ["Salons and spas", "Cosmetics brands", "Fitness and gyms"]),
    ("Energy and utilities", ["Solar and renewables", "Oil and gas", "Power and electricals",
                              "Water and waste management"]),
    ("Home services", ["Cleaning", "Plumbing and electrical", "Pest control",
                       "Repair and maintenance", "Interior design"]),
    ("Non-profit and government", ["NGOs and charities", "Government departments",
                                   "Religious and community organisations"]),
    ("Wholesale and distribution", ["FMCG distribution", "Industrial distribution",
                                    "Import and export", "Traders and stockists"]),
]


def slugify(name: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")
